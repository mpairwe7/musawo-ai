#!/usr/bin/env bash
# =============================================================================
# Musawo AI — Knowledge Base Reindexing Script
#
# Indexes MoH health guidelines into Qdrant vector store.
# Usage:
#   ./scripts/reindex.sh                # Full re-index
#   ./scripts/reindex.sh --check        # Health check only
# =============================================================================

set -euo pipefail

QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
COLLECTION="${QDRANT_COLLECTION:-musawo_health_kb}"
DENSE_MODEL="${DENSE_MODEL:-BAAI/bge-m3}"
DENSE_DIM="${DENSE_DIM:-1024}"
KB_DIR="${KB_DIR:-knowledge-base}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Pre-flight checks ──────────────────────────────────────────────────────

info "Checking Qdrant at ${QDRANT_URL}..."
if ! curl -sf "${QDRANT_URL}/healthz" > /dev/null 2>&1; then
    error "Qdrant is not reachable at ${QDRANT_URL}"
    error "Make sure Qdrant is running: docker compose up qdrant"
    exit 1
fi
info "Qdrant is healthy"

if [ "${1:-}" = "--check" ]; then
    info "Health check passed. Exiting."
    exit 0
fi

# ── Create / recreate collection ────────────────────────────────────────────

info "Creating collection '${COLLECTION}' (dense=${DENSE_DIM}d + sparse)..."

curl -sf -X PUT "${QDRANT_URL}/collections/${COLLECTION}" \
    -H "Content-Type: application/json" \
    -d '{
        "vectors": {
            "dense": {
                "size": '"${DENSE_DIM}"',
                "distance": "Cosine"
            }
        },
        "sparse_vectors": {
            "sparse": {}
        }
    }' > /dev/null

info "Collection created/updated"

# ── Index knowledge base ───────────────────────────────────────────────────

info "Indexing health knowledge base from ${KB_DIR}/..."

python3 - <<'PYEOF'
import json
import os
from pathlib import Path

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, NamedVector, NamedSparseVector, SparseVector

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.getenv("QDRANT_COLLECTION", "musawo_health_kb")
DENSE_MODEL = os.getenv("DENSE_MODEL", "BAAI/bge-m3")
KB_DIR = os.getenv("KB_DIR", "knowledge-base")

print(f"Loading encoder: {DENSE_MODEL}")
encoder = SentenceTransformer(DENSE_MODEL)

client = QdrantClient(url=QDRANT_URL)
points = []
point_id = 0

for json_file in Path(KB_DIR).rglob("*.json"):
    if json_file.name == "bm25_state.json":
        continue
    print(f"  Processing: {json_file}")
    data = json.loads(json_file.read_text())
    entries = data if isinstance(data, list) else data.get("entries", [])

    for entry in entries:
        text = entry.get("text", "") or entry.get("content", "")
        if not text.strip():
            continue

        dense_vec = encoder.encode(text).tolist()

        payload = {
            "text": text,
            "source": entry.get("source", json_file.stem),
            "section": entry.get("section", entry.get("topic", "")),
            "mode": entry.get("mode", "community"),
            "guideline": entry.get("guideline", ""),
            "severity": entry.get("severity", ""),
        }

        points.append(PointStruct(
            id=point_id,
            vector={"dense": dense_vec},
            payload=payload,
        ))
        point_id += 1

if points:
    # Batch upsert (100 at a time)
    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        client.upsert(collection_name=COLLECTION, points=batch)
        print(f"  Upserted {min(i + batch_size, len(points))}/{len(points)} points")

print(f"\nDone! Indexed {len(points)} passages into '{COLLECTION}'")
PYEOF

# ── Verify ──────────────────────────────────────────────────────────────────

COLLECTION_INFO=$(curl -sf "${QDRANT_URL}/collections/${COLLECTION}")
VECTORS_COUNT=$(echo "${COLLECTION_INFO}" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['vectors_count'])")

if [ "${VECTORS_COUNT}" -eq 0 ]; then
    error "Collection has 0 vectors — check your knowledge base files"
    exit 1
fi

info "Verification: ${VECTORS_COUNT} vectors in '${COLLECTION}'"
info "Reindex complete. Restart the API to pick up changes:"
info "  docker compose restart api"
