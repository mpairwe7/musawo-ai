# Crane Cloud Deployment — Musawo AI

Community Health Navigator for Rural Uganda, deployed on Crane Cloud RENU cluster.

## Production

| Field | Value |
|-------|-------|
| URL | https://musawo-ai-fae6b569.renu-01.cranecloud.io |
| Image | `landwind/musawo-ai:latest` |
| Size | ~5.5 GB |
| Port | 8080 (nginx → backend:8081 + frontend:3000) |
| Cluster | RENU (`9e81a70e-8460-4e5d-b0a8-17abcac30f68`) |
| Project ID | `3cc4bdd3-d085-449f-86e4-677dd791de7d` |
| App ID | `e45dd207-8483-4658-9ce1-8aa7702135c6` |

## Environment Variables

| Key | Value | Description |
|-----|-------|-------------|
| `LLM_BACKEND` | `passages` | Passage-based mode (no API key needed) |
| `PORT` | `8081` | Backend port (internal) |
| `LOG_LEVEL` | `info` | Logging level |

For LLM-powered responses, add:
- `GROQ_API_KEY` — free tier at console.groq.com
- `ANTHROPIC_API_KEY` — Claude API (optional fallback)

## Build & Deploy

```bash
# Build
docker build -t landwind/musawo-ai:latest -f Dockerfile.cranecloud .

# Test locally
docker run -d -p 8080:8080 landwind/musawo-ai:latest
curl http://localhost:8080/health

# Push to Docker Hub
docker push landwind/musawo-ai:latest
```

## Architecture

```
nginx:8080
  ├── /health, /chat, /chat/stream, /feedback, /facilities → uvicorn:8081
  ├── /_next/static/ → cached static assets
  └── / → Next.js:3000
```

Knowledge base (368K clinical guidelines) baked into image at `/app/knowledge-base/`.

## Verified Endpoints

- `/health` — `{"status": "ok", "mode": "offline", "llm_ready": true}`
- `/` — Frontend UI (HTTP 200)
- `/docs` — Swagger API docs (HTTP 200)
