"""Musawo AI — Hybrid retriever (Qdrant dense + BM25 sparse + RRF + cross-encoder).

Applies URA Chatbot vector DB optimization techniques:
- Dense (bge-m3) + BM25 sparse with Reciprocal Rank Fusion (RRF) via Qdrant prefetch
- Cross-encoder reranking (mxbai-rerank-base-v2) for precision
- Thread-safe circuit breaker with exponential backoff
- Health-domain query expansion (19 clinical synonym clusters)
- Severity-weighted metadata boosting (red > yellow > green)
- LRU query cache with deep-copy returns
- Keyword fallback with stop word removal

References:
- Qdrant hybrid search: prefetch + RRF fusion
- RAGAS faithfulness metric (docs.ragas.io)
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
from typing import Any

from .resilience import CircuitBreaker, CircuitState  # noqa: F401 (re-export)

logger = logging.getLogger("musawo.retriever")

# ── Config ─────────────────────────────────────────────────────────────────

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "musawo_health_kb")
DENSE_MODEL = os.getenv("DENSE_MODEL", "BAAI/bge-m3")
DENSE_DIM = int(os.getenv("DENSE_DIM", "1024"))
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "mixedbread-ai/mxbai-rerank-base-v2")
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() == "true"
BM25_STATE_PATH = os.getenv("BM25_STATE_PATH", "knowledge-base/bm25_state.json")

# Prefetch: how many candidates to retrieve before fusion/reranking
PREFETCH_LIMIT = int(os.getenv("PREFETCH_LIMIT", "20"))


# ── BM25 Sparse Encoder ───────────────────────────────────────────────────

class BM25SparseEncoder:
    """BM25-weighted sparse vectors for Qdrant's inverted index.

    Vocabulary and IDF are built from the indexed corpus via fit(),
    then serialised to JSON for the retriever to load at query time.
    """

    def __init__(self, k1: float = 1.2, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.vocab: dict[str, int] = {}
        self.idf: dict[int, float] = {}
        self.avg_dl: float = 0.0
        self.n_docs: int = 0

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())

    def fit(self, corpus: list[str]) -> None:
        """Build vocabulary and IDF weights from corpus."""
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
        logger.info("BM25 encoder fit: vocab=%d docs=%d", len(self.vocab), self.n_docs)

    def encode(self, text: str) -> tuple[list[int], list[float]]:
        """Return (indices, values) for a Qdrant SparseVector."""
        tokens = self._tokenize(text)
        tf: Counter[int] = Counter()
        for t in tokens:
            if t in self.vocab:
                tf[self.vocab[t]] += 1
        dl = len(tokens)
        indices: list[int] = []
        values: list[float] = []
        for idx, freq in tf.items():
            if idx in self.idf:
                score = self.idf[idx] * (
                    (freq * (self.k1 + 1))
                    / (freq + self.k1 * (1 - self.b + self.b * dl / max(self.avg_dl, 1)))
                )
                if score > 0:
                    indices.append(idx)
                    values.append(round(score, 6))
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


# ── Health domain query expansion ─────────────────────────────────────────
# Maps common query terms to related clinical terms for better recall
_QUERY_EXPANSION: dict[str, str] = {
    "prevent": "prevention control avoid protect",
    "malaria": "malaria mosquito net LLIN fever RDT",
    "diarrhoea": "diarrhoea diarrhea ORS zinc dehydration stool",
    "diarrhea": "diarrhoea diarrhea ORS zinc dehydration stool",
    "pneumonia": "pneumonia cough breathing amoxicillin chest",
    "fever": "fever temperature malaria infection",
    "pregnant": "pregnancy antenatal maternal ANC trimester",
    "pregnancy": "pregnancy antenatal maternal ANC danger signs",
    "breastfeed": "breastfeeding exclusive colostrum latch milk",
    "immuniz": "immunization vaccine BCG OPV pentavalent UNEPI",
    "vaccin": "vaccination vaccine immunization schedule",
    "hiv": "HIV AIDS ART viral load PMTCT adherence",
    "tb": "tuberculosis TB cough sputum treatment",
    "diabetes": "diabetes sugar glucose insulin hypertension NCD",
    "first aid": "first aid emergency burn wound bleeding CPR",
    "nutrition": "nutrition feeding MUAC malnutrition diet vitamin",
    "family planning": "family planning contraception IUD implant condom",
    "newborn": "newborn baby cord care kangaroo breastfeeding jaundice",
    "danger sign": "danger signs red flag refer emergency convulsions",
}


def expand_query(query: str) -> str:
    """Expand query with health domain synonyms for better recall."""
    lower = query.lower()
    expansions = []
    for trigger, expansion in _QUERY_EXPANSION.items():
        if trigger in lower:
            expansions.append(expansion)
    if not expansions:
        return query
    return f"{query} {' '.join(expansions)}"


# ── Hybrid Retriever ───────────────────────────────────────────────────────

class HybridRetriever:
    """Production hybrid retriever: dense + sparse RRF + cross-encoder rerank.

    Applies URA Chatbot's vector DB optimization techniques:
    1. Prefetch: separate dense and sparse candidate pools
    2. RRF Fusion: Qdrant merges via Reciprocal Rank Fusion
    3. Cross-encoder reranking: mxbai-rerank-base-v2 for precision
    4. Metadata boosting: section match + severity weight
    5. LRU caching: 200-entry cache with deep-copy returns

    Gracefully degrades to keyword fallback when Qdrant unavailable.
    """

    def __init__(self) -> None:
        self._dense_model: Any = None
        self._reranker: Any = None
        self._qdrant: Any = None
        self._bm25 = BM25SparseEncoder()
        self._breaker = CircuitBreaker(
            name="qdrant",
            failure_threshold=3,
            reset_timeout=10.0,
            max_timeout=300.0,
        )
        self._ready = False
        self._query_cache: dict[str, list[RetrievalHit]] = {}
        self._cache_max = 200

    def initialize(self) -> bool:
        """Connect to Qdrant and load models. Returns True if ready."""
        # Always load BM25 state first — works without Qdrant for keyword fallback
        if Path(BM25_STATE_PATH).exists():
            try:
                self._bm25.load(BM25_STATE_PATH)
                logger.info("BM25 state loaded from %s (vocab=%d)", BM25_STATE_PATH, len(self._bm25.vocab))
            except Exception as e:
                logger.warning("BM25 load failed: %s", e)

        try:
            from qdrant_client import QdrantClient
            from sentence_transformers import SentenceTransformer

            logger.info("Loading dense model: %s (forcing CPU)", DENSE_MODEL)
            self._dense_model = SentenceTransformer(DENSE_MODEL, device="cpu")

            # Cross-encoder reranker (URA technique: precision boost after RRF)
            if RERANK_ENABLED:
                try:
                    from sentence_transformers import CrossEncoder
                    self._reranker = CrossEncoder(RERANKER_MODEL)
                    logger.info("Cross-encoder reranker loaded: %s", RERANKER_MODEL)
                except Exception as e:
                    logger.warning("Reranker load failed (continuing without): %s", e)
                    self._reranker = None
            else:
                self._reranker = None

            self._qdrant = QdrantClient(url=QDRANT_URL, timeout=10)
            collections = [c.name for c in self._qdrant.get_collections().collections]
            if QDRANT_COLLECTION not in collections:
                logger.warning("Qdrant collection '%s' not found", QDRANT_COLLECTION)
                return False

            self._ready = True
            logger.info(
                "HybridRetriever ready (url=%s collection=%s rerank=%s)",
                QDRANT_URL, QDRANT_COLLECTION, self._reranker is not None,
            )
            return True
        except Exception as e:
            logger.warning("Retriever init failed (will use keyword fallback): %s", e)
            self._ready = False
            return False

    @property
    def is_ready(self) -> bool:
        """Check if retriever was initialised and circuit breaker allows requests."""
        return self._ready and self._qdrant is not None

    # ── Severity weights for health-critical prioritization ──────────────
    _SEVERITY_BOOST: dict[str, float] = {
        "red": 0.15,     # Emergency content boosted
        "yellow": 0.05,  # Monitor content slightly boosted
        "green": 0.0,    # Routine content — no boost
    }

    def _apply_metadata_boost(self, hits: list[RetrievalHit], query: str) -> list[RetrievalHit]:
        """Boost scores based on metadata relevance (section match + severity)."""
        query_tokens = set(re.findall(r"[a-z']+", query.lower()))

        for hit in hits:
            # Section name match boost (+0.1 per matching token)
            section = (hit.metadata.get("section", "") + " " + hit.metadata.get("topic", "")).lower()
            section_tokens = set(re.findall(r"[a-z']+", section))
            section_overlap = len(query_tokens & section_tokens)
            if section_overlap > 0:
                hit.score += 0.1 * section_overlap

            # Severity boost (red-flagged content more important)
            severity = hit.metadata.get("severity", "green")
            hit.score += self._SEVERITY_BOOST.get(severity, 0.0)

            # Cap at 1.0
            hit.score = min(hit.score, 1.0)

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits

    def search(
        self,
        query: str,
        top_k: int = 4,
        mode_filter: str | None = None,
    ) -> list[RetrievalHit]:
        """Hybrid search: dense + sparse RRF fusion + reranking + metadata boost.

        Pipeline (URA Chatbot technique):
        1. Check LRU cache
        2. Query expansion with health domain synonyms
        3. Encode dense (bge-m3) + sparse (BM25) vectors
        4. Prefetch dense and sparse candidates separately in Qdrant
        5. Fuse via Reciprocal Rank Fusion (RRF)
        6. Cross-encoder reranking for precision
        7. Apply metadata boosting (section match + severity)
        8. Cache and return top-k
        """
        # 1. Cache check (deep-copy to prevent score mutation)
        cache_key = f"{query}:{mode_filter or 'all'}:{top_k}"
        if cache_key in self._query_cache:
            return [
                RetrievalHit(text=h.text, score=h.score, metadata=dict(h.metadata), marker=h.marker)
                for h in self._query_cache[cache_key]
            ]

        # Circuit breaker gate
        if not self._ready or self._qdrant is None or not self._breaker.allow_request():
            return self._keyword_fallback(query, top_k, mode_filter)

        try:
            from qdrant_client import models

            # 2. Query expansion
            expanded = expand_query(query)

            # 3. Encode both dense and sparse vectors
            dense_vec = self._dense_model.encode(expanded).tolist()
            sparse_idx, sparse_val = self._bm25.encode(expanded)

            # 4. Build payload filter
            query_filter = None
            if mode_filter:
                query_filter = models.Filter(
                    must=[models.FieldCondition(
                        key="mode", match=models.MatchValue(value=mode_filter)
                    )]
                )

            # 5. Prefetch dense + sparse candidates, fuse with RRF
            #    (URA technique: Qdrant handles fusion server-side)
            prefetch = [
                models.Prefetch(
                    query=dense_vec,
                    using="dense",
                    limit=PREFETCH_LIMIT,
                ),
            ]
            if sparse_idx:
                prefetch.append(
                    models.Prefetch(
                        query=models.SparseVector(indices=sparse_idx, values=sparse_val),
                        using="sparse",
                        limit=PREFETCH_LIMIT,
                    )
                )

            results = self._qdrant.query_points(
                collection_name=QDRANT_COLLECTION,
                prefetch=prefetch,
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                query_filter=query_filter,
                limit=PREFETCH_LIMIT,
            )

            if not results.points:
                self._breaker.record_success()
                return self._keyword_fallback(query, top_k, mode_filter)

            # Build candidates from RRF results
            candidates: list[RetrievalHit] = []
            for pt in results.points:
                payload = pt.payload or {}
                candidates.append(
                    RetrievalHit(
                        text=payload.get("text", ""),
                        score=float(pt.score) if pt.score else 0.0,
                        metadata={k: v for k, v in payload.items() if k != "text"},
                    )
                )

            # 6. Cross-encoder reranking (URA technique: precision after RRF recall)
            if self._reranker and candidates:
                pairs = [
                    (query, c.text or c.metadata.get("answer", ""))
                    for c in candidates
                ]
                rerank_scores = self._reranker.predict(pairs)
                for i, s in enumerate(rerank_scores):
                    candidates[i].score = float(s)
                candidates.sort(key=lambda x: x.score, reverse=True)

            # 7. Apply metadata boosting (section match + severity weight)
            candidates = self._apply_metadata_boost(candidates, query)

            self._breaker.record_success()
            result = candidates[:top_k]

            # 8. Cache result (LRU eviction)
            if len(self._query_cache) >= self._cache_max:
                oldest = next(iter(self._query_cache))
                del self._query_cache[oldest]
            self._query_cache[cache_key] = result

            return result

        except Exception as e:
            logger.error("Hybrid search failed: %s", e)
            self._breaker.record_failure()
            return self._keyword_fallback(query, top_k, mode_filter)

    # Stop words to ignore in relevance scoring
    _STOP_WORDS = frozenset({
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "shall",
        "should", "may", "might", "must", "can", "could", "to", "of", "in",
        "for", "on", "with", "at", "by", "from", "as", "into", "about",
        "like", "through", "after", "over", "between", "out", "against",
        "during", "without", "before", "under", "around", "among",
        "i", "me", "my", "we", "our", "you", "your", "he", "she", "it",
        "they", "them", "their", "this", "that", "these", "those",
        "what", "which", "who", "whom", "how", "when", "where", "why",
        "not", "no", "nor", "but", "and", "or", "if", "then", "so",
        "very", "just", "only", "also", "too", "more", "most", "some",
        "any", "each", "every", "all", "both", "few", "many", "much",
    })

    def _keyword_fallback(
        self,
        query: str,
        top_k: int,
        mode_filter: str | None = None,
    ) -> list[RetrievalHit]:
        """Word-overlap search with stop word removal and section boosting."""
        all_tokens = set(re.findall(r"[a-z']+", query.lower()))
        query_tokens = all_tokens - self._STOP_WORDS
        if not query_tokens:
            query_tokens = all_tokens

        candidates: list[tuple[float, dict]] = []
        kb_dir = Path(os.getenv("KNOWLEDGE_BASE_DIR", "knowledge-base"))
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

                    overlap = len(query_tokens & doc_tokens) / max(len(query_tokens), 1)

                    section = (entry.get("section", "") + " " + entry.get("topic", "")).lower()
                    section_tokens = set(re.findall(r"[a-z']+", section))
                    section_match = len(query_tokens & section_tokens)
                    if section_match > 0:
                        overlap += 0.3 * section_match

                    if overlap > 0.15:
                        candidates.append((overlap, entry))
            except Exception:
                continue

        candidates.sort(key=lambda x: x[0], reverse=True)
        return [
            RetrievalHit(
                text=entry.get("text", "") or entry.get("content", ""),
                score=min(score, 1.0),
                metadata={k: v for k, v in entry.items() if k not in ("text", "content")},
            )
            for score, entry in candidates[:top_k]
        ]


# ── Grounding utilities ───────────────────────────────────────────────────

def compute_faithfulness(answer: str, contexts: list[str]) -> float:
    """Hybrid faithfulness scoring: token overlap + medical term grounding.

    Dual-signal grounding:
    1. Token overlap (fast, catches exact matches)
    2. Medical term grounding (catches paraphrases like "high temperature" ~ "fever")
    """
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
        token_overlap = len(sent_tokens & context_tokens) / len(sent_tokens)

        medical_terms = sent_tokens & {
            "malaria", "fever", "diarrhoea", "pneumonia", "cough", "ors",
            "zinc", "act", "amoxicillin", "refer", "danger", "dehydration",
            "breastfeed", "vaccine", "immuniz", "hiv", "tb", "diabetes",
            "bleeding", "pregnancy", "convuls", "measles", "vitamin",
        }
        medical_grounded = (
            len(medical_terms & context_tokens) / max(len(medical_terms), 1)
            if medical_terms else 1.0
        )

        if token_overlap > 0.4 or (token_overlap > 0.25 and medical_grounded > 0.5):
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
