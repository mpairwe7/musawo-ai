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
    )
    ESCALATION_TOTAL = Counter(
        "musawo_escalation_total",
        "Queries requiring human/facility escalation",
    )
    FEEDBACK_TOTAL = Counter(
        "musawo_feedback_total",
        "Feedback submissions",
        ["rating"],
    )
    LLM_FALLBACK_TOTAL = Counter(
        "musawo_llm_fallback_total",
        "Times Claude API failed and system fell back to local model",
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


def record_abstention() -> None:
    if PROMETHEUS_AVAILABLE:
        ABSTENTION_TOTAL.inc()


def record_escalation() -> None:
    if PROMETHEUS_AVAILABLE:
        ESCALATION_TOTAL.inc()


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


def get_metrics_text() -> tuple[str, str]:
    """Return (metrics_text, content_type) for /metrics endpoint."""
    if PROMETHEUS_AVAILABLE:
        return generate_latest().decode("utf-8"), CONTENT_TYPE_LATEST
    return "# prometheus_client not installed\n", "text/plain"
