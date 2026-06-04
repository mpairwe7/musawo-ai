"""Musawo AI — Prometheus metrics for production observability.

Exposes counters, histograms, and gauges for:
- Query volume by mode
- Triage severity distribution
- Red-flag detection rate
- Response latency (retrieval + LLM)
- Abstention and escalation rates
- Active sessions
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Generator

try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

# ── Counters ───────────────────────────────────────────────────────────

if PROMETHEUS_AVAILABLE:
    QUERY_TOTAL = Counter(
        "musawo_query_total",
        "Total queries processed",
        ["mode", "locale"],
    )
    TRIAGE_TOTAL = Counter(
        "musawo_triage_total",
        "Triage assessments by severity",
        ["severity"],
    )
    RED_FLAG_TOTAL = Counter(
        "musawo_red_flag_detections_total",
        "Danger signs detected",
        ["symptom"],
    )
    ABSTENTION_TOTAL = Counter(
        "musawo_abstention_total",
        "Queries where system abstained due to low confidence",
        ["locale"],
    )
    ESCALATION_TOTAL = Counter(
        "musawo_escalation_total",
        "Queries requiring human/facility escalation",
        ["locale"],
    )
    LANG_MISMATCH_TOTAL = Counter(
        "musawo_language_mismatch_total",
        "Responses where detected language didn't match requested locale",
        ["expected", "detected"],
    )
    CONFIDENCE_BY_LOCALE = Histogram(
        "musawo_confidence_by_locale",
        "Retrieval confidence scores by locale",
        ["locale"],
        buckets=[0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0],
    )
    FEEDBACK_TOTAL = Counter(
        "musawo_feedback_total",
        "Feedback submissions",
        ["rating"],
    )
    LLM_FALLBACK_TOTAL = Counter(
        "musawo_llm_fallback_total",
        "Times the primary LLM failed and the system fell back to a lower tier",
    )

    # ── Histograms ─────────────────────────────────────────────────────

    RETRIEVAL_LATENCY = Histogram(
        "musawo_retrieval_latency_seconds",
        "Time spent in hybrid retrieval",
        buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
    )
    LLM_LATENCY = Histogram(
        "musawo_llm_latency_seconds",
        "Time spent in LLM generation",
        buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
    )
    TOTAL_LATENCY = Histogram(
        "musawo_total_latency_seconds",
        "Total request latency (end-to-end)",
        buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
    )

    # ── Gauges ─────────────────────────────────────────────────────────

    ACTIVE_SESSIONS = Gauge(
        "musawo_active_sessions",
        "Number of active chat sessions",
    )
    KB_ENTRIES = Gauge(
        "musawo_knowledge_base_entries",
        "Number of entries in knowledge base",
    )


# ── Helper functions ───────────────────────────────────────────────────

def record_query(mode: str, locale: str) -> None:
    if PROMETHEUS_AVAILABLE:
        QUERY_TOTAL.labels(mode=mode, locale=locale).inc()


def record_triage(severity: str) -> None:
    if PROMETHEUS_AVAILABLE:
        TRIAGE_TOTAL.labels(severity=severity).inc()


def record_red_flag(symptom: str) -> None:
    if PROMETHEUS_AVAILABLE:
        RED_FLAG_TOTAL.labels(symptom=symptom).inc()


def record_abstention(locale: str = "en") -> None:
    if PROMETHEUS_AVAILABLE:
        ABSTENTION_TOTAL.labels(locale=locale).inc()


def record_escalation(locale: str = "en") -> None:
    if PROMETHEUS_AVAILABLE:
        ESCALATION_TOTAL.labels(locale=locale).inc()


def record_lang_mismatch(expected: str, detected: str) -> None:
    if PROMETHEUS_AVAILABLE:
        LANG_MISMATCH_TOTAL.labels(expected=expected, detected=detected).inc()


def record_confidence(locale: str, score: float) -> None:
    if PROMETHEUS_AVAILABLE:
        CONFIDENCE_BY_LOCALE.labels(locale=locale).observe(score)


def record_feedback(rating: int) -> None:
    if PROMETHEUS_AVAILABLE:
        FEEDBACK_TOTAL.labels(rating=str(rating)).inc()


def record_llm_fallback() -> None:
    if PROMETHEUS_AVAILABLE:
        LLM_FALLBACK_TOTAL.inc()


def set_active_sessions(count: int) -> None:
    if PROMETHEUS_AVAILABLE:
        ACTIVE_SESSIONS.set(count)


def set_kb_entries(count: int) -> None:
    if PROMETHEUS_AVAILABLE:
        KB_ENTRIES.set(count)


@contextmanager
def observe_retrieval_latency() -> Generator[None, None, None]:
    if PROMETHEUS_AVAILABLE:
        with RETRIEVAL_LATENCY.time():
            yield
    else:
        yield


@contextmanager
def observe_llm_latency() -> Generator[None, None, None]:
    if PROMETHEUS_AVAILABLE:
        with LLM_LATENCY.time():
            yield
    else:
        yield


@contextmanager
def observe_total_latency() -> Generator[None, None, None]:
    if PROMETHEUS_AVAILABLE:
        with TOTAL_LATENCY.time():
            yield
    else:
        yield


# ── Voice metrics ─────────────────────────────────────────────────────────
if PROMETHEUS_AVAILABLE:
    VOICE_ASR_LATENCY = Histogram(
        "musawo_voice_asr_latency_seconds",
        "Voice ASR processing latency",
        buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
    )
    VOICE_TTS_LATENCY = Histogram(
        "musawo_voice_tts_first_chunk_seconds",
        "Time to first TTS audio chunk",
        buckets=[0.1, 0.25, 0.5, 1.0, 2.0],
    )
    VOICE_SESSION_TOTAL = Counter(
        "musawo_voice_session_total",
        "Total voice sessions started",
    )
    VOICE_BARGE_IN_TOTAL = Counter(
        "musawo_voice_barge_in_total",
        "Total barge-in interruptions",
    )
    VOICE_UTTERANCE_DURATION = Histogram(
        "musawo_voice_utterance_duration_seconds",
        "Duration of user utterances",
        buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
    )
else:
    VOICE_ASR_LATENCY = None  # type: ignore[assignment]
    VOICE_TTS_LATENCY = None  # type: ignore[assignment]
    VOICE_SESSION_TOTAL = None  # type: ignore[assignment]
    VOICE_BARGE_IN_TOTAL = None  # type: ignore[assignment]
    VOICE_UTTERANCE_DURATION = None  # type: ignore[assignment]


def record_voice_session() -> None:
    if PROMETHEUS_AVAILABLE and VOICE_SESSION_TOTAL:
        VOICE_SESSION_TOTAL.inc()


def record_voice_barge_in() -> None:
    if PROMETHEUS_AVAILABLE and VOICE_BARGE_IN_TOTAL:
        VOICE_BARGE_IN_TOTAL.inc()


def record_voice_asr_latency(seconds: float) -> None:
    if PROMETHEUS_AVAILABLE and VOICE_ASR_LATENCY:
        VOICE_ASR_LATENCY.observe(seconds)


def record_voice_tts_latency(seconds: float) -> None:
    if PROMETHEUS_AVAILABLE and VOICE_TTS_LATENCY:
        VOICE_TTS_LATENCY.observe(seconds)


def record_voice_utterance_duration(seconds: float) -> None:
    if PROMETHEUS_AVAILABLE and VOICE_UTTERANCE_DURATION:
        VOICE_UTTERANCE_DURATION.observe(seconds)


def get_metrics_text() -> tuple[str, str]:
    """Return (metrics_text, content_type) for /metrics endpoint."""
    if PROMETHEUS_AVAILABLE:
        return generate_latest().decode("utf-8"), CONTENT_TYPE_LATEST
    return "# prometheus_client not installed\n", "text/plain"
