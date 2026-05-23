"""Tests for Musawo AI retriever — BM25, circuit breaker, grounding, citations.

Tests cover:
- BM25SparseEncoder: tokenize, fit, encode, save/load roundtrip
- CircuitBreaker: closed → open → half-open lifecycle
- compute_faithfulness: edge cases and overlap scoring
- build_citations: structured output from RetrievalHit list
- HybridRetriever: keyword fallback when Qdrant is unavailable
"""

import json
import os
import tempfile

import pytest
from unittest.mock import patch, MagicMock

from app.retriever import (
    BM25SparseEncoder,
    RetrievalHit,
    HybridRetriever,
    compute_faithfulness,
    build_citations,
)
from app.resilience import CircuitBreaker, CircuitState


# ── BM25SparseEncoder ─────────────────────────────────────────────────────


class TestBM25SparseEncoder:
    """BM25SparseEncoder tokenization, fitting, encoding, and persistence."""

    def test_tokenize_extracts_lowercase_words(self):
        enc = BM25SparseEncoder()
        tokens = enc._tokenize("Fever AND Diarrhoea treatment for Children")
        assert "fever" in tokens
        assert "diarrhoea" in tokens
        assert "children" in tokens
        # Uppercase originals should not appear
        assert "Fever" not in tokens

    def test_tokenize_handles_punctuation(self):
        enc = BM25SparseEncoder()
        tokens = enc._tokenize("ORS+Zinc — 200mg, twice/day!")
        assert "ors" in tokens
        assert "zinc" in tokens
        assert "200mg" in tokens  # \w+ keeps numerics attached (better for dosages)

    def test_fit_builds_vocab_and_idf(self):
        enc = BM25SparseEncoder()
        corpus = [
            "child has fever and malaria",
            "pregnant mother with headache",
            "fever and diarrhoea in child",
        ]
        enc.fit(corpus)

        assert enc.n_docs == 3
        assert enc.avg_dl > 0
        assert "fever" in enc.vocab
        assert "child" in enc.vocab
        # IDF values must exist for vocab entries
        fever_idx = enc.vocab["fever"]
        assert fever_idx in enc.idf

    def test_encode_returns_indices_and_values(self):
        enc = BM25SparseEncoder()
        corpus = [
            "child has fever and malaria",
            "pregnant mother with headache",
            "fever and diarrhoea in child",
        ]
        enc.fit(corpus)

        indices, values = enc.encode("child with fever")
        assert len(indices) > 0
        assert len(indices) == len(values)
        # All scores should be positive
        assert all(v > 0 for v in values)

    def test_encode_unknown_tokens_ignored(self):
        enc = BM25SparseEncoder()
        enc.fit(["fever malaria child"])
        indices, values = enc.encode("xyz qqq zzz")
        assert indices == []
        assert values == []

    def test_save_load_roundtrip(self):
        enc = BM25SparseEncoder()
        corpus = ["child has fever", "pregnant mother bleeding"]
        enc.fit(corpus)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name

        try:
            enc.save(path)

            enc2 = BM25SparseEncoder()
            enc2.load(path)

            assert enc2.vocab == enc.vocab
            assert enc2.n_docs == enc.n_docs
            assert enc2.avg_dl == enc.avg_dl
            # IDF keys are ints after round-trip
            assert enc2.idf == enc.idf
        finally:
            os.unlink(path)


# ── CircuitBreaker ─────────────────────────────────────────────────────────


class TestCircuitBreaker:
    """CircuitBreaker lifecycle: closed → open → half-open (thread-safe)."""

    def test_starts_closed(self):
        cb = CircuitBreaker(name="test")
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_opens_after_reaching_threshold(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_resets_on_success(self):
        cb = CircuitBreaker(name="test", failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, reset_timeout=0.0)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN or cb.state == CircuitState.HALF_OPEN
        # With reset_timeout=0.0, the next state check transitions to half-open
        assert cb.allow_request() is True  # half-open allows one retry

    def test_exponential_backoff_on_half_open_failure(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, reset_timeout=0.01)
        cb.record_failure()  # → OPEN
        import time
        time.sleep(0.02)  # Wait for reset_timeout
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()  # HALF_OPEN → OPEN with doubled timeout
        assert cb._current_timeout == 0.02  # doubled from 0.01


# ── compute_faithfulness ───────────────────────────────────────────────────


class TestComputeFaithfulness:
    """compute_faithfulness: grounding fraction of answer sentences."""

    def test_empty_answer_returns_zero(self):
        assert compute_faithfulness("", ["some context"]) == 0.0

    def test_empty_contexts_returns_zero(self):
        assert compute_faithfulness("This is an answer.", []) == 0.0

    def test_fully_grounded_returns_one(self):
        context = "The child has fever and needs ORS and zinc treatment at home."
        answer = "The child has fever and needs ORS and zinc treatment at home."
        score = compute_faithfulness(answer, [context])
        assert score == 1.0

    def test_partial_overlap_returns_fraction(self):
        context = "Give ORS and zinc for diarrhoea in children under five."
        answer = (
            "Give ORS and zinc for diarrhoea in children. "
            "Quantum entanglement is unrelated to medicine entirely."
        )
        score = compute_faithfulness(answer, [context])
        assert 0.0 < score < 1.0

    def test_short_sentences_skipped(self):
        # Sentences <= 10 chars are filtered out; if all filtered, return 1.0
        score = compute_faithfulness("OK. Yes.", ["something"])
        assert score == 1.0


# ── build_citations ────────────────────────────────────────────────────────


class TestBuildCitations:
    """build_citations: structured citation list from RetrievalHit list."""

    def test_empty_list(self):
        assert build_citations([]) == []

    def test_single_hit_structure(self):
        hit = RetrievalHit(
            text="Give ORS and zinc for diarrhoea.",
            score=0.85,
            metadata={"source": "MoH VHT Guide", "section": "Diarrhoea", "page": "12"},
        )
        cites = build_citations([hit])
        assert len(cites) == 1
        assert cites[0]["ref"] == "[1]"
        assert cites[0]["source"] == "MoH VHT Guide"
        assert cites[0]["section"] == "Diarrhoea"
        assert cites[0]["page"] == "12"
        assert "ORS" in cites[0]["passage"]

    def test_multiple_hits_numbered(self):
        hits = [
            RetrievalHit(text="Passage one text.", score=0.9, metadata={"source": "A"}),
            RetrievalHit(text="Passage two text.", score=0.7, metadata={"source": "B"}),
        ]
        cites = build_citations(hits)
        assert cites[0]["ref"] == "[1]"
        assert cites[1]["ref"] == "[2]"

    def test_missing_metadata_uses_defaults(self):
        hit = RetrievalHit(text="Some passage text.", score=0.5, metadata={})
        cites = build_citations([hit])
        assert cites[0]["source"] == "MoH Guidelines"
        assert cites[0]["section"] == ""

    def test_long_passage_truncated(self):
        long_text = "A" * 300
        hit = RetrievalHit(text=long_text, score=0.6, metadata={"source": "X"})
        cites = build_citations([hit])
        assert cites[0]["passage"].endswith("...")
        assert len(cites[0]["passage"]) == 203  # 200 chars + "..."


# ── HybridRetriever keyword fallback ──────────────────────────────────────


class TestHybridRetrieverFallback:
    """HybridRetriever falls back to keyword search when not ready."""

    def test_not_ready_by_default(self):
        r = HybridRetriever()
        assert r.is_ready is False

    def test_keyword_fallback_when_not_ready(self):
        """Keyword fallback returns a list even when Qdrant is unavailable."""
        r = HybridRetriever()
        assert r.is_ready is False
        # search() should use _keyword_fallback, which returns a list
        hits = r.search("diarrhoea children ORS zinc", top_k=2)
        assert isinstance(hits, list)

    def test_search_delegates_to_keyword_fallback_when_breaker_open(self):
        r = HybridRetriever()
        r._ready = True
        r._qdrant = MagicMock()
        # Force the breaker open
        for _ in range(5):
            r._breaker.record_failure()
        assert r._breaker.allow_request() is False
        # search() should use _keyword_fallback, which returns a list
        hits = r.search("fever malaria", top_k=2)
        assert isinstance(hits, list)


# ── RetrievalHit ──────────────────────────────────────────────────────────


class TestRetrievalHit:
    """RetrievalHit auto-generates a marker from text hash."""

    def test_marker_auto_generated(self):
        hit = RetrievalHit(text="sample passage", score=0.5)
        assert hit.marker.startswith("p-")
        assert len(hit.marker) == 14  # "p-" + 12 hex chars

    def test_custom_marker_preserved(self):
        hit = RetrievalHit(text="sample", score=0.5, marker="custom-id")
        assert hit.marker == "custom-id"
