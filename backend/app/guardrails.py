"""Musawo AI — Health-specific guardrails (OWASP LLM Top 10 2025).

Adaptations from the URA Chatbot guardrails for health context:
- Never diagnose — guidance only
- PII redaction with Uganda health-ID patterns
- Red-flag escalation for danger signs
- Confidence scoring with mandatory abstention
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# ── Configuration ──────────────────────────────────────────────────────────

MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "2000"))
ABSTENTION_THRESHOLD = float(os.getenv("ABSTENTION_THRESHOLD", "0.15"))
ESCALATION_THRESHOLD = float(os.getenv("ESCALATION_THRESHOLD", "0.25"))
GROUNDING_THRESHOLD = float(os.getenv("GROUNDING_THRESHOLD", "0.3"))


@dataclass
class GuardResult:
    allowed: bool
    reason: str = ""
    flags: list[str] = field(default_factory=list)


# ── Prompt injection patterns (LLM01) ─────────────────────────────────────

_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(r"you\s+are\s+now\s+(?:a|an|the)\s+", re.I),
    re.compile(r"system\s*:", re.I),
    re.compile(r"<\|system\|>", re.I),
    re.compile(r"ADMIN\s*MODE", re.I),
    re.compile(r"JAILBREAK", re.I),
    re.compile(r"DAN\s+mode", re.I),
    re.compile(r"reveal\s+your\s+(system\s+)?prompt", re.I),
    re.compile(r"pretend\s+you\s+(are|have)\s+no\s+(rules|restrictions)", re.I),
    re.compile(r"do\s+anything\s+now", re.I),
    re.compile(r"act\s+as\s+(?:a\s+)?doctor\s+and\s+diagnose", re.I),
]

# ── Harmful health intent patterns ─────────────────────────────────────────

_HARMFUL_PATTERNS: list[re.Pattern] = [
    re.compile(r"prescri(?:be|ption)\s+(?:me|for)", re.I),
    re.compile(r"give\s+me\s+(?:a\s+)?diagnosis", re.I),
    re.compile(r"(buy|sell|smuggle)\s+(?:controlled|narcotic|drug)", re.I),
    re.compile(r"(fake|forge|fabricate)\s+(?:medical|health)\s+(?:cert|report|record)", re.I),
    re.compile(r"(abort|terminate)\s+(?:pregnancy|baby)", re.I),
    re.compile(r"sui?cid", re.I),
    re.compile(r"(harm|hurt|kill)\s+(?:my|the)?\s*(?:self|baby|child)", re.I),
    re.compile(r"(poison|overdose)", re.I),
]

# ── PII patterns (Uganda-specific, LLM02) ─────────────────────────────────

_PII_PATTERNS: dict[str, re.Pattern] = {
    "EMAIL": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "UG_PHONE": re.compile(r"(?:\+256|0)(?:7|4)\d{8}"),
    "UG_NIN": re.compile(r"C[MF]\d{2}[A-Z]{5}\d{5}[A-Z]"),
    "CREDIT_CARD": re.compile(r"(?:\d{4}[-\s]?){3}\d{4}"),
    "UG_PASSPORT": re.compile(r"[A-Z]{2}\d{7}"),
    # Health-specific
    "HIV_STATUS": re.compile(r"\b(?:hiv\s*(?:positive|negative|\+|-))\b", re.I),
    "ART_NUMBER": re.compile(r"\bART[-/]?\d{4,}\b", re.I),
}


class InputGuard:
    """Validates user input before processing."""

    @staticmethod
    def check(text: str) -> GuardResult:
        if not text or not text.strip():
            return GuardResult(allowed=False, reason="Empty input.")

        if len(text) > MAX_INPUT_LENGTH:
            return GuardResult(
                allowed=False,
                reason=f"Input exceeds {MAX_INPUT_LENGTH} characters.",
            )

        # Prompt injection
        for pat in _INJECTION_PATTERNS:
            if pat.search(text):
                return GuardResult(
                    allowed=False,
                    reason="Input blocked by safety filter.",
                    flags=["prompt_injection"],
                )

        # Harmful intent
        for pat in _HARMFUL_PATTERNS:
            if pat.search(text):
                # Suicide / self-harm → special escalation
                if "suicid" in text.lower() or "harm" in text.lower():
                    return GuardResult(
                        allowed=False,
                        reason=(
                            "If you or someone you know is in crisis, please call the "
                            "Uganda National Mental Health Hotline: 0800 100 263 (toll-free) "
                            "or visit the nearest health facility immediately."
                        ),
                        flags=["crisis_escalation"],
                    )
                return GuardResult(
                    allowed=False,
                    reason=(
                        "I can only provide health guidance — I cannot prescribe, "
                        "diagnose, or assist with harmful activities. Please consult "
                        "a qualified health worker."
                    ),
                    flags=["harmful_intent"],
                )

        return GuardResult(allowed=True)


class OutputGuard:
    """Post-generation safety checks."""

    @staticmethod
    def redact_pii(text: str) -> str:
        """Replace PII with redaction markers."""
        for label, pat in _PII_PATTERNS.items():
            text = pat.sub(f"[REDACTED_{label}]", text)
        return text

    @staticmethod
    def sanitize(text: str) -> str:
        """Strip HTML / script injection from LLM output."""
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", "", text)
        return text

    @staticmethod
    def check_prompt_leakage(text: str) -> bool:
        """Detect if the model regurgitated system prompt fragments."""
        leakage_signals = [
            "you are musawo",
            "your system prompt",
            "your instructions say",
            "SYSTEM:",
            "<<SYS>>",
        ]
        lower = text.lower()
        return any(sig.lower() in lower for sig in leakage_signals)

    @staticmethod
    def should_abstain(best_score: float | None, hits_count: int) -> bool:
        """Refuse to answer if retrieval confidence is too low."""
        if hits_count == 0:
            return True
        if best_score is not None and best_score < ABSTENTION_THRESHOLD:
            return True
        return False

    @staticmethod
    def should_escalate(
        faithfulness: float | None,
        hits_count: int,
    ) -> bool:
        """Flag for human/facility escalation."""
        if hits_count == 0:
            return True
        if faithfulness is not None and faithfulness < ESCALATION_THRESHOLD:
            return True
        return False

    @staticmethod
    def enforce_disclaimer(text: str) -> str:
        """Ensure every response includes the health disclaimer."""
        disclaimer = (
            "\n\n---\n*This is health guidance only — not a medical diagnosis. "
            "If symptoms worsen or you are unsure, visit the nearest health "
            "facility or call the toll-free health hotline: 0800 100 263.*"
        )
        if "not a medical diagnosis" not in text.lower():
            text += disclaimer
        return text

    @staticmethod
    def check_grounding(
        text: str, faithfulness: float | None
    ) -> str:
        """Append low-grounding warning if needed."""
        if faithfulness is not None and faithfulness < GROUNDING_THRESHOLD:
            text += (
                "\n\n**Note:** This response may not be fully supported by "
                "the official health guidelines. Please verify with a "
                "qualified health worker."
            )
        return text


def scan_retrieved_text(text: str) -> tuple[str, bool]:
    """Scrub indirect injection attempts from retrieved passages."""
    scrubbed = False
    for pat in _INJECTION_PATTERNS:
        if pat.search(text):
            text = pat.sub("[SCRUBBED]", text)
            scrubbed = True
    return text, scrubbed
