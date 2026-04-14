"""Musawo AI — Core health service orchestrator.

Pipeline: InputGuard → Supervisor → Cache → Retrieval → Abstention → LLM → OutputGuard
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Generator

from app.agents.supervisor import classify
from app.agents.triage_agent import TriageAgent
from app.guardrails import InputGuard, OutputGuard, scan_retrieved_text
from app.llm import (
    format_passages,
    generate,
    is_ready as llm_is_ready,
    stream_tokens,
)
from app.models import (
    ChatRequest,
    ChatResponse,
    Citation,
    EscalationAction,
    Mode,
    RedFlag,
    Severity,
    TriageResult,
)
from app.retriever import (
    HybridRetriever,
    build_citations,
    compute_faithfulness,
)

logger = logging.getLogger("musawo.service")

# ── Config ─────────────────────────────────────────────────────────────────

LLM_DEADLINE_SECONDS = int(os.getenv("LLM_INFERENCE_TIMEOUT", "45"))
GROUNDING_THRESHOLD = float(os.getenv("GROUNDING_THRESHOLD", "0.3"))
SESSION_TTL = int(os.getenv("SESSION_TTL_SECONDS", "86400"))
MAX_SESSIONS = 5000
MAX_HISTORY = 40
HISTORY_WINDOW = 10  # Last 10 turn-pairs sent to LLM for deep context
LLM_WORKERS = int(os.getenv("LLM_WORKERS", "2"))

# Emergency contacts (Uganda)
EMERGENCY_CONTACTS = {
    "health_hotline": "0800 100 263 (toll-free)",
    "ambulance": "0800 911 911",
    "mental_health": "0800 100 263",
    "maternal_hotline": "0800 100 263",
}


# ── Session store ──────────────────────────────────────────────────────────

@dataclass
class Session:
    history: deque = field(default_factory=lambda: deque(maxlen=MAX_HISTORY))
    created: float = field(default_factory=time.monotonic)
    last_active: float = field(default_factory=time.monotonic)
    mode: Mode = Mode.COMMUNITY
    pregnancy_week: int | None = None


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._lock = Lock()

    def get_or_create(self, session_id: str | None) -> tuple[str, Session]:
        with self._lock:
            if not session_id:
                session_id = str(uuid.uuid4())

            if session_id in self._sessions:
                session = self._sessions[session_id]
                session.last_active = time.monotonic()
                return session_id, session

            # Evict stale sessions
            if len(self._sessions) >= MAX_SESSIONS:
                stale = sorted(
                    self._sessions.items(),
                    key=lambda x: x[1].last_active,
                )
                evict_count = len(stale) // 4
                for sid, _ in stale[:evict_count]:
                    del self._sessions[sid]
                logger.info("Evicted %d stale sessions", evict_count)

            session = Session()
            self._sessions[session_id] = session
            return session_id, session

    def update_session(self, session_id: str, mode: Mode | None = None,
                       pregnancy_week: int | None = None,
                       history_entry: dict | None = None) -> None:
        """Thread-safe session mutation."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return
            if mode is not None:
                session.mode = mode
            if pregnancy_week is not None:
                session.pregnancy_week = pregnancy_week
            if history_entry is not None:
                session.history.append(history_entry)

    def get_history(self, session_id: str, window: int = HISTORY_WINDOW) -> list[dict]:
        """Thread-safe history read."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return []
            return list(session.history)[-window * 2:]


# ── Health Service ─────────────────────────────────────────────────────────

class HealthService:
    """Main orchestrator for Musawo health guidance pipeline."""

    def __init__(self) -> None:
        self.retriever = HybridRetriever()
        self.sessions = SessionStore()
        self.triage_agent = TriageAgent()
        self._executor = ThreadPoolExecutor(max_workers=LLM_WORKERS)
        self._ready = False

    def initialize(self) -> None:
        """Warm up retriever and verify LLM connectivity."""
        retriever_ok = self.retriever.initialize()
        llm_ok = llm_is_ready()
        self._ready = True
        logger.info(
            "HealthService initialized (retriever=%s, llm=%s)",
            retriever_ok,
            llm_ok,
        )

    @property
    def is_ready(self) -> bool:
        return self._ready

    def generate(self, req: ChatRequest) -> ChatResponse:
        """Synchronous health guidance generation."""
        # 1. Input guard
        guard = InputGuard.check(req.query)
        if not guard.allowed:
            return ChatResponse(
                answer=guard.reason,
                mode=req.mode,
                locale=req.locale,
                confidence=0.0,
                escalation_required="crisis" in (guard.flags or []),
                escalation_message=guard.reason if "crisis" in (guard.flags or []) else None,
            )

        # 2. Session (thread-safe)
        session_id, session = self.sessions.get_or_create(req.session_id)
        self.sessions.update_session(session_id, mode=req.mode, pregnancy_week=req.pregnancy_week)

        # 3. Supervisor routing
        route = classify(req.query, current_mode=req.mode)
        effective_mode = route.mode

        # 4. Retrieval — try mode-filtered first, fall back to unfiltered
        hits = self.retriever.search(
            query=req.query,
            top_k=4,
            mode_filter=effective_mode.value,
        )
        # If mode filter returns too few/weak results, search across all modes
        if len(hits) < 2 or (hits and max(h.score for h in hits) < 0.3):
            all_hits = self.retriever.search(query=req.query, top_k=4, mode_filter=None)
            if all_hits and (not hits or max(h.score for h in all_hits) > max((h.score for h in hits), default=0)):
                hits = all_hits

        # Scrub retrieved passages for indirect injection
        for hit in hits:
            hit.text, _ = scan_retrieved_text(hit.text)

        # 5. Abstention check
        best_score = max((h.score for h in hits), default=0.0)
        if OutputGuard.should_abstain(best_score if hits else None, len(hits)):
            return ChatResponse(
                answer=(
                    "I don't have enough information in the health guidelines to "
                    "answer this question reliably. Please visit your nearest health "
                    f"facility or call the health hotline: {EMERGENCY_CONTACTS['health_hotline']}."
                ),
                mode=effective_mode,
                locale=req.locale,
                confidence=0.0,
                escalation_required=True,
                escalation_message="Low confidence — recommend facility visit.",
                session_id=session_id,
            )

        # 6. Build history for LLM (thread-safe read)
        history_msgs = self.sessions.get_history(session_id)

        # 7. LLM generation with deadline
        passages = [
            {"text": h.text, "source": h.metadata.get("source", "MoH"), "section": h.metadata.get("section", "")}
            for h in hits
        ]

        try:
            future = self._executor.submit(
                generate,
                query=req.query,
                passages=passages,
                mode=effective_mode.value,
                history=history_msgs,
                locale=req.locale.value,
            )
            result = future.result(timeout=LLM_DEADLINE_SECONDS)
            answer_text = result["text"]
        except TimeoutError:
            logger.warning("LLM timed out after %ds", LLM_DEADLINE_SECONDS)
            # Fallback: return best passage
            answer_text = (
                f"I'm having trouble generating a response right now. "
                f"Based on the guidelines, here's what may help:\n\n"
                f"{hits[0].text if hits else 'Please visit your nearest health facility.'}"
            )
        except Exception as e:
            logger.error("LLM generation failed: %s", e)
            answer_text = (
                f"I'm temporarily unable to generate a response. "
                f"Please try again, or call the health hotline: "
                f"{EMERGENCY_CONTACTS['health_hotline']}."
            )

        # 8. Output guards
        answer_text = OutputGuard.redact_pii(answer_text)
        answer_text = OutputGuard.sanitize(answer_text)

        if OutputGuard.check_prompt_leakage(answer_text):
            answer_text = (
                "I apologize, but I had trouble generating a proper response. "
                "Please rephrase your question."
            )

        # 9. Grounding
        contexts = [h.text for h in hits]
        faithfulness = compute_faithfulness(answer_text, contexts)
        answer_text = OutputGuard.check_grounding(answer_text, faithfulness)
        answer_text = OutputGuard.enforce_disclaimer(answer_text)

        # 10. Triage (VHT mode)
        triage = None
        if effective_mode == Mode.VHT:
            triage = self._build_triage(route, hits)

        # 11. Escalation check
        escalation = OutputGuard.should_escalate(faithfulness, len(hits))
        if route.detected_symptoms:
            escalation = True

        # 12. Citations
        citations = [
            Citation(**c) for c in build_citations(hits)
        ]

        # 13. Update session history (thread-safe)
        self.sessions.update_session(session_id, history_entry={"role": "user", "content": req.query})
        self.sessions.update_session(session_id, history_entry={"role": "assistant", "content": answer_text})

        return ChatResponse(
            answer=answer_text,
            mode=effective_mode,
            locale=req.locale,
            confidence=round(min(best_score, faithfulness) if faithfulness else best_score, 3),
            citations=citations,
            faithfulness_score=round(faithfulness, 3) if faithfulness else None,
            triage=triage,
            escalation_required=escalation,
            escalation_message=(
                f"Please visit the nearest health facility or call "
                f"{EMERGENCY_CONTACTS['health_hotline']}."
                if escalation else None
            ),
            session_id=session_id,
        )

    def stream_response(self, req: ChatRequest) -> Generator[dict[str, Any], None, None]:
        """SSE streaming response generator."""
        # Input guard
        guard = InputGuard.check(req.query)
        if not guard.allowed:
            yield {"event": "error", "data": guard.reason}
            return

        session_id, _ = self.sessions.get_or_create(req.session_id)
        self.sessions.update_session(session_id, mode=req.mode)

        route = classify(req.query, current_mode=req.mode)
        effective_mode = route.mode

        hits = self.retriever.search(
            query=req.query, top_k=4, mode_filter=effective_mode.value
        )
        for hit in hits:
            hit.text, _ = scan_retrieved_text(hit.text)

        best_score = max((h.score for h in hits), default=0.0)
        citations = build_citations(hits)

        # Metadata event
        triage = None
        if effective_mode == Mode.VHT:
            triage = self._build_triage(route, hits)

        yield {
            "event": "metadata",
            "data": {
                "mode": effective_mode.value,
                "citations": citations,
                "session_id": session_id,
                "triage": triage.model_dump() if triage else None,
                "red_flags": route.detected_symptoms,
            },
        }

        # Abstention
        if OutputGuard.should_abstain(best_score if hits else None, len(hits)):
            msg = (
                "I don't have enough information to answer reliably. "
                f"Please call {EMERGENCY_CONTACTS['health_hotline']} or visit the nearest facility."
            )
            yield {"event": "data", "data": msg}
            yield {"event": "done", "data": ""}
            return

        # Stream tokens
        passages = [
            {"text": h.text, "source": h.metadata.get("source", "MoH"), "section": h.metadata.get("section", "")}
            for h in hits
        ]
        history_msgs = self.sessions.get_history(session_id)

        full_answer = ""
        for chunk in stream_tokens(
            query=req.query,
            passages=passages,
            mode=effective_mode.value,
            history=history_msgs,
            locale=req.locale.value,
        ):
            if chunk["type"] == "token":
                full_answer += chunk["text"]
                yield {"event": "data", "data": chunk["text"]}
            elif chunk["type"] == "done":
                break

        # Post-stream grounding
        contexts = [h.text for h in hits]
        faithfulness = compute_faithfulness(full_answer, contexts)
        escalation = OutputGuard.should_escalate(faithfulness, len(hits))

        yield {
            "event": "grounding",
            "data": {
                "faithfulness_score": round(faithfulness, 3),
                "grounding_warning": faithfulness < GROUNDING_THRESHOLD,
                "escalation_required": escalation or bool(route.detected_symptoms),
            },
        }

        # Update session (thread-safe)
        self.sessions.update_session(session_id, history_entry={"role": "user", "content": req.query})
        self.sessions.update_session(session_id, history_entry={"role": "assistant", "content": full_answer})

        yield {"event": "done", "data": ""}

    def _build_triage(self, route, hits) -> TriageResult | None:
        """Build VHT triage result from routing and retrieval."""
        if not route.detected_symptoms:
            return TriageResult(
                severity=route.severity_hint or Severity.GREEN,
                manage_at_home=["Follow standard iCCM assessment protocol."],
            )

        red_flags = [
            RedFlag(
                symptom=symptom,
                severity=Severity.RED,
                action=EscalationAction.EMERGENCY_REFER,
                detail=f"Danger sign detected: {symptom}. Refer immediately.",
            )
            for symptom in route.detected_symptoms
        ]

        return TriageResult(
            severity=Severity.RED,
            red_flags=red_flags,
            refer_reasons=route.detected_symptoms,
            follow_up="Reassess within 24 hours if referred patient returns.",
        )
