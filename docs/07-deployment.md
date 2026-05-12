# Crane Cloud Deployment — Musawo AI v2.6

Community Health Navigator for Rural Uganda, deployed on Crane Cloud RENU cluster.

## Production

| Field | Value |
|-------|-------|
| URL | https://musawo-ai-cc3230cc.renu-01.cranecloud.io |
| Image | `landwind/musawo-ai:latest` |
| Size (v2.5) | ~5.5 GB |
| Size (v2.6 optimized) | ~1.2 GB (target) |
| Port | 8080 (nginx → backend:8081 + frontend:3000) |
| Cluster | RENU (`9e81a70e-8460-4e5d-b0a8-17abcac30f68`) |
| App ID | `205f5e2a-e029-4f3e-b567-5f1f32cffde6` |
| GitHub | https://github.com/mpairwe7/musawo-ai |

## v2.6 Image Size Reduction

The optimized Dockerfile (`Dockerfile.cranecloud.optimized`) reduces image size from ~5.5 GB to ~1.2 GB:

| Optimization | Savings |
|-------------|---------|
| Node Alpine frontend builder | ~400 MB |
| Aggressive venv cleanup (pyc, dist-info, tests, docs) | ~800 MB |
| Gzip compression in nginx | Transfer size reduction |
| No build tools in runtime stage | ~600 MB |
| Total estimated reduction | ~4.3 GB |

## Environment Variables

| Key | Value | Description |
|-----|-------|-------------|
| `LLM_BACKEND` | `groq` | LLM provider (groq/claude/local/passages) |
| `GROQ_API_KEY` | `gsk_...` (secret) | Groq free tier API key |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model |
| `PORT` | `8081` | Backend port (internal) |
| `BM25_STATE_PATH` | `/app/knowledge-base/bm25_state.json` | Pre-built BM25 index |
| `KNOWLEDGE_BASE_DIR` | `/app/knowledge-base` | Clinical guidelines directory |
| `LOG_LEVEL` | `info` | Logging level |

## LLM Backend Priority

```
Groq (free, fast) → Claude API → Local Qwen3 → Passage-based fallback
```

- **Groq**: Free tier, ~500 tok/s, `llama-3.3-70b-versatile` or `qwen/qwen3-32b`
- **Claude**: Set `ANTHROPIC_API_KEY` for Claude Sonnet with extended thinking
- **Local Qwen3**: Set `LLM_BACKEND=local`, needs GPU or GGUF quantized model
- **Passages**: Always works, returns text from guidelines without LLM

## Retrieval Architecture

Without Qdrant (Crane Cloud), the app uses **BM25 keyword fallback**:

1. `bm25_state.json` baked into image at build time (4353 terms, 20 docs)
2. `_keyword_fallback()` searches knowledge-base JSON files by word overlap
3. Retrieved passages are passed to Groq LLM for grounded response generation
4. `OutputGuard.should_abstain()` blocks low-confidence responses (safety)

**Key fix for Crane Cloud:** BM25 loads *before* Qdrant init, so keyword fallback works even when Qdrant is unavailable. The `KNOWLEDGE_BASE_DIR` env var ensures absolute path resolution.

## Build & Deploy

### v2.6 Optimized Build (recommended)

```bash
# Build with optimized Dockerfile
docker build -t landwind/musawo-ai:v2.6 -f Dockerfile.cranecloud.optimized .

# Verify image size
docker images landwind/musawo-ai:v2.6 --format '{{.Size}}'

# Test locally
docker run -d -p 8080:8080 \
  -e GROQ_API_KEY=gsk_your_key \
  -e LLM_BACKEND=groq \
  landwind/musawo-ai:v2.6

# Push
docker tag landwind/musawo-ai:v2.6 landwind/musawo-ai:latest
docker push landwind/musawo-ai:latest
```

### Legacy Build (v2.5)

```bash
# Build with original Dockerfile
docker build -t landwind/musawo-ai:latest -f Dockerfile.cranecloud .

# Test locally
docker run -d -p 8080:8080 \
  -e GROQ_API_KEY=gsk_your_key \
  -e LLM_BACKEND=groq \
  landwind/musawo-ai:latest

# Push
docker push landwind/musawo-ai:latest
```

## Verified Endpoints (2026-05-12)

| Endpoint | Status | Response |
|----------|--------|----------|
| `/health` | 200 | `{"status":"ok","llm_ready":true}` |
| `/v1/chat` | 200 | Groq LLM response, confidence ~0.97 |
| `/v1/modes` | 200 | 3 modes: vht, maternal, community |
| `/v1/facilities` | 200 | 20 health facilities |
| `/v1/emergency-contacts` | 200 | 5 emergency contacts |
| `/v1/triage` | 200 | iCCM assessment with follow-up questions |
| `/v1/chat/stream` | 200 | SSE streaming with metadata + triage |
| `/` | 200 | "Musawo AI — Community Health Navigator" |
| `/docs` | 200 | Swagger API documentation |

## Local Qwen3 Inference (GPU)

For offline/GPU deployment with quantized Qwen3:

```bash
# GGUF (CPU, ~4GB RAM via llama.cpp)
docker run -d -p 8080:8080 \
  -e LLM_BACKEND=local \
  -e GGUF_MODEL_PATH=/app/models/qwen3-8b-q4_k_m.gguf \
  -v ./models:/app/models \
  landwind/musawo-ai:latest

# 4-bit quantized (GPU, ~4GB VRAM via bitsandbytes)
docker run -d --gpus '"device=0"' -p 8080:8080 \
  -e LLM_BACKEND=local \
  -e LLM_MODEL=Qwen/Qwen3-8B \
  landwind/musawo-ai:latest
```

The local model loading strategy: GGUF → 4-bit BnB → full precision (auto-detected).

## Voice Streaming (Added 2026-05-12)

WebSocket endpoint `/v1/voice/chat/stream` added for real-time voice conversations.

| Feature | Status |
|---------|--------|
| Energy-based VAD | Enabled |
| Sentence-chunked TTS | Enabled |
| Barge-in | Enabled |
| Sunbird STT/TTS | Requires `SUNBIRD_API_TOKEN` |
| Multilingual (lg/nyn/sw) | Via Sunbird MT |

See `docs/voice-system.md` for full protocol documentation.

### Updated Production URL

```
https://musawo-ai-c29604f0.renu-01.cranecloud.io
```
