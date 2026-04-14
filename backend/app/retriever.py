"""Musawo AI — Hybrid retriever (Qdrant dense + BM25 sparse + cross-encoder).

Forked from URA Chatbot retriever, adapted for health knowledge base:
- MoH VHT guidelines, maternal protocols, community health
- Metadata: guideline, section, severity, mode (vht/maternal/community)
- Circuit breaker for resilience
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger("musawo.retriever")

# ── Config ─────────────────────────────────────────────────────────────────

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "musawo_health_kb")
DENSE_MODEL = os.getenv("DENSE_MODEL", "BAAI/bge-m3")
DENSE_DIM = int(os.getenv("DENSE_DIM", "1024"))
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "mixedbread-ai/mxbai-rerank-base-v2")
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() == "true"
BM25_STATE_PATH = os.getenv("BM25_STATE_PATH", "knowledge-base/bm25_state.json")

# Circuit breaker
CB_FAILURE_THRESHOLD = 3
CB_RESET_TIMEOUT = 10.0


# ── Circuit Breaker ────────────────────────────────────────────────────────

@dataclass
class CircuitBreaker:
    failure_threshold: int = CB_FAILURE_THRESHOLD
    reset_timeout: float = CB_RESET_TIMEOUT
    _failures: int = 0
    _last_failure: float = 0.0
    _open: bool = False

    def record_failure(self) -> None:
        self._failures += 1
        self._last_failure = time.monotonic()
        if self._failures >= self.failure_threshold:
            self._open = True
            logger.warning("Circuit breaker OPEN after %d failures", self._failures)

    def record_success(self) -> None:
        self._failures = 0
        self._open = False

    @property
    def is_open(self) -> bool:
        if self._open and (time.monotonic() - self._last_failure) > self.reset_timeout:
            self._open = False  # half-open: allow one retry
            logger.info("Circuit breaker half-open, allowing retry")
        return self._open


# ── BM25 Sparse Encoder ───────────────────────────────────────────────────

class BM25SparseEncoder:
    """Lightweight BM25 for sparse vector construction."""

    def __init__(self, k1: float = 1.2, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.vocab: dict[str, int] = {}
        self.idf: dict[int, float] = {}
        self.avg_dl: float = 0.0
        self.n_docs: int = 0

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"[a-z']+", text.lower())

    def fit(self, corpus: list[str]) -> None:
        self.n_docs = len(corpus)
        doc_freq: Counter[int] = Counter()
        total_len = 0
        for doc in corpus:
            tokens = self._tokenize(doc)
            total_len += len(tokens)
            seen: set[int] = set()
            for t in tokens:
                if t not in self.vocab:
                    self.vocab[t] = len(self.vocab)
                idx = self.vocab[t]
                if idx not in seen:
                    doc_freq[idx] += 1
                    seen.add(idx)
        self.avg_dl = total_len / max(self.n_docs, 1)
        for idx, df in doc_freq.items():
            self.idf[idx] = math.log((self.n_docs - df + 0.5) / (df + 0.5) + 1.0)

    def encode(self, text: str) -> tuple[list[int], list[float]]:
        tokens = self._tokenize(text)
        tf: Counter[int] = Counter()
        for t in tokens:
            if t in self.vocab:
                tf[self.vocab[t]] += 1
        dl = len(tokens)
        indices, values = [], []
        for idx, freq in tf.items():
            if idx in self.idf:
                score = self.idf[idx] * (
                    (freq * (self.k1 + 1))
                    / (freq + self.k1 * (1 - self.b + self.b * dl / max(self.avg_dl, 1)))
                )
                indices.append(idx)
                values.append(score)
        return indices, values

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(
                {"vocab": self.vocab, "idf": {str(k): v for k, v in self.idf.items()},
                 "avg_dl": self.avg_dl, "n_docs": self.n_docs},
                f,
            )

    def load(self, path: str) -> None:
        with open(path) as f:
            state = json.load(f)
        self.vocab = state["vocab"]
        self.idf = {int(k): v for k, v in state["idf"].items()}
        self.avg_dl = state["avg_dl"]
        self.n_docs = state["n_docs"]


# ── Hit dataclass ──────────────────────────────────────────────────────────

@dataclass
class RetrievalHit:
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)
    marker: str = ""

    def __post_init__(self):
        if not self.marker:
            h = hashlib.sha256(self.text.encode()).hexdigest()[:12]
            self.marker = f"p-{h}"


# ── Hybrid Retriever ───────────────────────────────────────────────────────

class HybridRetriever:
    """Qdrant hybrid search with dense + sparse + optional reranking."""

    def __init__(self) -> None:
        self._dense_model = None
        self._reranker = None
        self._qdrant = None
        self._bm25 = BM25SparseEncoder()
        self._breaker = CircuitBreaker()
        self._ready = False

    def initialize(self) -> bool:
        """Load models and connect to Qdrant. Returns True if ready."""
        try:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading dense model: %s", DENSE_MODEL)
            self._dense_model = SentenceTransformer(DENSE_MODEL)

            if RERANK_ENABLED:
                from sentence_transformers import CrossEncoder
                logger.info("Loading reranker: %s", RERANKER_MODEL)
                self._reranker = CrossEncoder(RERANKER_MODEL)

            from qdrant_client import QdrantClient
            self._qdrant = QdrantClient(url=QDRANT_URL, timeout=30)
            self._qdrant.get_collection(QDRANT_COLLECTION)

            # Load BM25 state if available
            if Path(BM25_STATE_PATH).exists():
                self._bm25.load(BM25_STATE_PATH)
                logger.info("BM25 state loaded from %s", BM25_STATE_PATH)

            self._ready = True
            logger.info("HybridRetriever ready (dense=%s, rerank=%s)", DENSE_MODEL, RERANK_ENABLED)
            return True
        except Exception as e:
            logger.warning("Retriever init failed (will use keyword fallback): %s", e)
            self._ready = False
            return False

    @property
    def is_ready(self) -> bool:
        return self._ready and not self._breaker.is_open

    def search(
        self,
        query: str,
        top_k: int = 4,
        mode_filter: str | None = None,
    ) -> list[RetrievalHit]:
        """Hybrid search with RRF fusion and optional reranking."""
        if not self.is_ready:
            return self._keyword_fallback(query, top_k, mode_filter)

        try:
            from qdrant_client.models import (
                FieldCondition,
                Filter,
                MatchValue,
                NamedSparseVector,
                NamedVector,
                Prefetch,
                SparseVector,
            )

            # Encode query
            dense_vec = self._dense_model.encode(query).tolist()  # type: ignore[union-attr]
            sparse_idx, sparse_val = self._bm25.encode(query)

            # Build filter
            qdrant_filter = None
            if mode_filter:
                qdrant_filter = Filter(
                    must=[FieldCondition(key="mode", match=MatchValue(value=mode_filter))]
                )

            # Prefetch: dense + sparse → RRF fusion
            prefetches = [
                Prefetch(
                    query=NamedVector(name="dense", vector=dense_vec),
                    using="dense",
                    limit=20,
                    filter=qdrant_filter,
                ),
            ]
            if sparse_idx:
                prefetches.append(
                    Prefetch(
                        query=NamedSparseVector(
                            name="sparse",
                            vector=SparseVector(indices=sparse_idx, values=sparse_val),
                        ),
                        using="sparse",
                        limit=20,
                        filter=qdrant_filter,
                    )
                )

            results = self._qdrant.query_points(  # type: ignore[union-attr]
                collection_name=QDRANT_COLLECTION,
                prefetch=prefetches,
                query=NamedVector(name="dense", vector=dense_vec),
                using="dense",
                limit=20,
                with_payload=True,
            )

            hits = []
            for pt in results.points:
                payload = pt.payload or {}
                hits.append(
                    RetrievalHit(
                        text=payload.get("text", ""),
                        score=pt.score or 0.0,
                        metadata={
                            k: v
                            for k, v in payload.items()
                            if k != "text"
                        },
                    )
                )

            # Rerank if enabled
            if self._reranker and hits:
                pairs = [(query, h.text) for h in hits]
                rerank_scores = self._reranker.predict(pairs)
                for h, s in zip(hits, rerank_scores):
                    h.score = float(s)
                hits.sort(key=lambda h: h.score, reverse=True)

            self._breaker.record_success()
            return hits[:top_k]

        except Exception as e:
            logger.error("Qdrant search failed: %s", e)
            self._breaker.record_failure()
            return self._keyword_fallback(query, top_k, mode_filter)

    def _keyword_fallback(
        self,
        query: str,
        top_k: int,
        mode_filter: str | None = None,
    ) -> list[RetrievalHit]:
        """Word-overlap search on local JSON knowledge base."""
        query_tokens = set(re.findall(r"[a-z']+", query.lower()))
        if not query_tokens:
            return []

        candidates: list[tuple[float, dict]] = []
        kb_dir = Path("knowledge-base")
        for json_file in kb_dir.rglob("*.json"):
            if json_file.name == "bm25_state.json":
                continue
            try:
                data = json.loads(json_file.read_text())
                entries = data if isinstance(data, list) else data.get("entries", [])
                for entry in entries:
                    if mode_filter and entry.get("mode", "") != mode_filter:
                        continue
                    text = entry.get("text", "") or entry.get("content", "")
                    doc_tokens = set(re.findall(r"[a-z']+", text.lower()))
                    if not doc_tokens:
                        continue
                    overlap = len(query_tokens & doc_tokens) / len(query_tokens)
                    if overlap > 0.1:
                        candidates.append((overlap, entry))
            except Exception:
                continue

        candidates.sort(key=lambda x: x[0], reverse=True)
        return [
            RetrievalHit(
                text=entry.get("text", "") or entry.get("content", ""),
                score=score,
                metadata={k: v for k, v in entry.items() if k not in ("text", "content")},
            )
            for score, entry in candidates[:top_k]
        ]


# ── Grounding utilities ───────────────────────────────────────────────────

def compute_faithfulness(answer: str, contexts: list[str]) -> float:
    """Lightweight faithfulness proxy: fraction of answer sentences grounded."""
    if not answer or not contexts:
        return 0.0

    sentences = re.split(r"[.!?]+", answer)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    if not sentences:
        return 1.0

    context_tokens = set()
    for ctx in contexts:
        context_tokens.update(re.findall(r"[a-z']+", ctx.lower()))

    grounded = 0
    for sent in sentences:
        sent_tokens = set(re.findall(r"[a-z']+", sent.lower()))
        if not sent_tokens:
            continue
        overlap = len(sent_tokens & context_tokens) / len(sent_tokens)
        if overlap > 0.5:
            grounded += 1

    return grounded / len(sentences)


def build_citations(hits: list[RetrievalHit]) -> list[dict[str, str]]:
    """Build citation list from retrieval hits."""
    citations = []
    for i, hit in enumerate(hits):
        meta = hit.metadata
        citations.append({
            "ref": f"[{i + 1}]",
            "source": meta.get("source", meta.get("guideline", "MoH Guidelines")),
            "page": str(meta.get("page", "")),
            "section": meta.get("section", meta.get("topic", "")),
            "passage": hit.text[:200] + ("..." if len(hit.text) > 200 else ""),
        })
    return citations
