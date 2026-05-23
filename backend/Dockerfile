FROM python:3.11.11-slim AS base

# System deps for torch + sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create audit log directory
RUN mkdir -p /app/logs

# Non-root user (security)
RUN useradd -m -r musawo && chown -R musawo:musawo /app
USER musawo

# Default env for production
ENV APP_ENV=production \
    AUDIT_LOG_PATH=/app/logs/audit.jsonl \
    WORKERS=2

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

# Multiple workers for production resilience (2-4 recommended)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WORKERS}"]
