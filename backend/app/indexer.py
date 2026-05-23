"""Document indexing pipeline for Musawo's Qdrant vector store.

Ported from URA Chatbot indexer, adapted for health knowledge base:
- Ingests JSON knowledge base entries (MoH guidelines, protocols)
- Sentence-boundary chunking with overlap for long passages
- Dual vectors: dense (bge-m3) + BM25 sparse (inverted index)
- Batch upsert with UUID point IDs
- Collection schema: dense cosine + sparse index (in-memory)

Usage:
    python -m backend.app.indexer                # full reindex
    python -m backend.app.indexer --recreate     # drop + rebuild collection
    python -m backend.app.indexer --dir path/    # custom KB directory
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger("musawo.indexer")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "musawo_health_kb")
DENSE_MODEL_NAME = os.getenv("DENSE_MODEL", "BAAI/bge-m3")
DENSE_DIM = int(os.getenv("DENSE_DIM", "1024"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "600"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))
BATCH_SIZE = int(os.getenv("INDEX_BATCH_SIZE", "64"))

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
KB_DIR = Path(os.getenv("KB_DIR", str(_PROJECT_ROOT / "knowledge-base")))
BM25_STATE_PATH = Path(
    os.getenv("BM25_STATE_PATH", str(KB_DIR / "bm25_state.json"))
)


# ---------------------------------------------------------------------------
# Sentence-boundary chunking (from URA)
# ---------------------------------------------------------------------------
def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks, breaking at sentence boundaries.

    Prefers breaks at: ". " → ".\n" → "\n\n" → "\n" → " "
    Skips chunks shorter than 50 characters.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            # Try to find a natural break point in the second half of the chunk
            for sep in [". ", ".\n", "\n\n", "\n", " "]:
                idx = text.rfind(sep, start + chunk_size // 2, end)
                if idx > start:
                    end = idx + len(sep)
                    break
        chunks.append(text[start:end].strip())
        start = end - overlap

    return [c for c in chunks if len(c) > 50]


# ---------------------------------------------------------------------------
# Knowledge base ingestor
# ---------------------------------------------------------------------------
def ingest_knowledge_base(kb_dir: Path) -> list[dict[str, Any]]:
    """Load and chunk all JSON knowledge base entries.

    Each entry becomes one or more documents with metadata preserved.
    Long passages are chunked with overlap for better retrieval granularity.
    """
    documents: list[dict[str, Any]] = []
    if not kb_dir.is_dir():
        logger.error("Knowledge base directory not found: %s", kb_dir)
        return documents

    for json_file in sorted(kb_dir.rglob("*.json")):
        if json_file.name == "bm25_state.json":
            continue

        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            entries = data if isinstance(data, list) else data.get("entries", [data])

            chunk_idx = 0
            for entry in entries:
                text = entry.get("text", "") or entry.get("content", "")
                if not text or len(text.strip()) < 20:
                    continue

                # Determine mode from directory structure or entry metadata
                mode = entry.get("mode", "")
                if not mode:
                    rel_path = str(json_file.relative_to(kb_dir)).lower()
                    if "maternal" in rel_path or "obstetric" in rel_path or "neonatal" in rel_path:
                        mode = "maternal"
                    elif "vht" in rel_path or "iccm" in rel_path:
                        mode = "vht"
                    else:
                        mode = "community"

                # Chunk long passages for better retrieval granularity
                text_chunks = chunk_text(text)

                for chunk in text_chunks:
                    # Extract section from first heading if present
                    section = entry.get("section", "") or entry.get("topic", "")
                    if not section:
                        for line in chunk.split("\n"):
                            stripped = line.strip()
                            if stripped.startswith("#"):
                                section = stripped.lstrip("#").strip()
                                break

                    documents.append({
                        "text": chunk,
                        "source": entry.get("source", json_file.stem),
                        "chunk_id": f"{json_file.stem}_chunk_{chunk_idx}",
                        "section": section,
                        "topic": entry.get("topic", ""),
                        "mode": mode,
                        "guideline": entry.get("guideline", ""),
                        "severity": entry.get("severity", "green"),
                        "condition": entry.get("condition", ""),
                    })
                    chunk_idx += 1

            if chunk_idx > 0:
                logger.info("Ingested %s: %d chunks", json_file.name, chunk_idx)

        except Exception:
            logger.exception("Failed to ingest %s", json_file.name)

    return documents


# ---------------------------------------------------------------------------
# Index builder
# ---------------------------------------------------------------------------
def build_index(
    documents: list[dict[str, Any]],
    recreate: bool = False,
) -> dict[str, Any]:
    """Embed documents and upsert into Qdrant with dense + sparse vectors.

    Applies URA's indexing strategy:
    1. Create collection with dense (cosine) + sparse (in-memory) vector configs
    2. Fit BM25 encoder on corpus for sparse vectors
    3. Batch encode with bge-m3 for dense vectors
    4. Upsert points with both vector types for RRF hybrid search
    """
    from qdrant_client import QdrantClient, models
    from sentence_transformers import SentenceTransformer

    from .retriever import BM25SparseEncoder

    client = QdrantClient(url=QDRANT_URL, timeout=30)
    dense_model = SentenceTransformer(DENSE_MODEL_NAME, device="cpu")

    # -- Collection management -----------------------------------------------
    existing = [c.name for c in client.get_collections().collections]
    if recreate and QDRANT_COLLECTION in existing:
        client.delete_collection(QDRANT_COLLECTION)
        logger.info("Deleted existing collection '%s'", QDRANT_COLLECTION)
        existing.remove(QDRANT_COLLECTION)

    if QDRANT_COLLECTION not in existing:
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config={
                "dense": models.VectorParams(
                    size=DENSE_DIM,
                    distance=models.Distance.COSINE,
                ),
            },
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(
                    index=models.SparseIndexParams(on_disk=False),
                ),
            },
        )
        logger.info(
            "Created Qdrant collection '%s' (dense=%d-dim cosine + sparse BM25)",
            QDRANT_COLLECTION,
            DENSE_DIM,
        )

    # -- BM25 sparse encoder: fit on corpus ----------------------------------
    texts = [d["text"] for d in documents]
    sparse_encoder = BM25SparseEncoder()
    sparse_encoder.fit(texts)

    BM25_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    sparse_encoder.save(str(BM25_STATE_PATH))
    logger.info("Saved BM25 state to %s (vocab=%d)", BM25_STATE_PATH, len(sparse_encoder.vocab))

    # -- Batch embed + upsert ------------------------------------------------
    total_upserted = 0
    for i in range(0, len(documents), BATCH_SIZE):
        batch = documents[i: i + BATCH_SIZE]
        batch_texts = [d["text"] for d in batch]

        # Dense embeddings (batch for efficiency)
        dense_embeddings = dense_model.encode(batch_texts, show_progress_bar=False)

        points: list[models.PointStruct] = []
        for j, doc in enumerate(batch):
            # Sparse vector from BM25
            sparse_idx, sparse_val = sparse_encoder.encode(doc["text"])
            vectors: dict[str, Any] = {"dense": dense_embeddings[j].tolist()}
            if sparse_idx:
                vectors["sparse"] = models.SparseVector(
                    indices=sparse_idx, values=sparse_val
                )

            # Payload = all metadata (text included for retrieval)
            payload = dict(doc.items())
            points.append(
                models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vectors,
                    payload=payload,
                )
            )

        client.upsert(collection_name=QDRANT_COLLECTION, points=points)
        total_upserted += len(points)
        logger.info(
            "Upserted batch %d–%d (%d/%d)",
            i, i + len(batch), total_upserted, len(documents),
        )

    stats = {
        "collection": QDRANT_COLLECTION,
        "total_documents": len(documents),
        "total_upserted": total_upserted,
        "vocab_size": len(sparse_encoder.vocab),
        "modes": {
            "vht": sum(1 for d in documents if d.get("mode") == "vht"),
            "maternal": sum(1 for d in documents if d.get("mode") == "maternal"),
            "community": sum(1 for d in documents if d.get("mode") == "community"),
        },
    }
    logger.info("Indexing complete: %s", stats)
    return stats


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main() -> None:
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Index Musawo knowledge base into Qdrant")
    parser.add_argument("--recreate", action="store_true", help="Drop and recreate collection")
    parser.add_argument("--dir", type=str, default=str(KB_DIR), help="Knowledge base directory")
    args = parser.parse_args()

    documents = ingest_knowledge_base(Path(args.dir))

    if not documents:
        logger.error("No documents to index")
        return

    build_index(documents, recreate=args.recreate)


if __name__ == "__main__":
    main()
