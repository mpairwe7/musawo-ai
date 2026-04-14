# ===========================================================================
# Musawo AI — HuggingFace Spaces Docker Deployment
#
# Single container that runs both the FastAPI backend and serves
# the Next.js frontend build via the same uvicorn process.
#
# HF Spaces expects app on port 7860.
# ===========================================================================

FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl nodejs npm && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Backend deps ───────────────────────────────────────────────────────
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# ── Frontend build ─────────────────────────────────────────────────────
COPY frontend/package.json frontend/package-lock.json* /app/frontend/
RUN cd /app/frontend && npm install --omit=dev 2>/dev/null || npm install

COPY frontend/ /app/frontend/
RUN cd /app/frontend && npm run build || true

# ── Copy backend + knowledge base ──────────────────────────────────────
COPY backend/ /app/backend/
COPY knowledge-base/ /app/knowledge-base/
COPY scripts/ /app/scripts/

# ── Startup script ─────────────────────────────────────────────────────
COPY <<'STARTUP' /app/start.sh
#!/bin/bash
set -e

echo "Starting Musawo AI on port 7860..."

# Start backend API
cd /app/backend
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 7860 \
    --workers 1 \
    --timeout-keep-alive 30
STARTUP

RUN chmod +x /app/start.sh

# Non-root user (HF Spaces requirement)
RUN useradd -m -u 1000 musawo && chown -R musawo:musawo /app
USER musawo

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -sf http://localhost:7860/health || exit 1

CMD ["/app/start.sh"]
