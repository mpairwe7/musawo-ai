"""Musawo AI — centralized, typed configuration (single source of truth).

Every environment variable the backend understands is declared here once, with a
type and an exact default. Modules import `settings` instead of calling
`os.getenv` directly, so the configuration surface is discoverable, validated,
and kept in sync with `.env.example`.

Design notes:
- One flat `Settings` model so field access is `settings.groq_api_key` and the
  env-var name maps 1:1 (case-insensitively) to the field name.
- `extra="ignore"` is mandatory: the deployment `.env` may carry unrelated keys
  (fork leftovers, PaaS credentials). Unknown keys must never crash boot.
- Secrets default to "" and are never logged (see `main.py` startup summary).
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-root .env (the app runs from backend/, the .env lives at the project root).
_ENV_FILE = str(Path(__file__).resolve().parents[2] / ".env")

_DEFAULT_ORIGINS = (
    "http://localhost:3000,http://localhost:3200,"
    "http://localhost:8000,http://localhost:8888,"
    "http://127.0.0.1:3200,http://127.0.0.1:8888"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # tolerate AGRILINK_*/CRANE_CLOUD_*/etc. in the .env
    )

    # ── Application / server (main.py) ──────────────────────────────────────
    log_level: str = "INFO"
    app_env: str = "development"
    port: int = 8000
    allowed_origins: str = _DEFAULT_ORIGINS  # CSV; split + dev-IP logic in main.py
    rate_limit_requests: int = 30
    rate_limit_window: int = 60
    sms_api_key: str = ""  # secret — gates POST /v1/sms/send
    max_audio_size: int = 10 * 1024 * 1024  # 10 MB

    # ── LLM backend selection (llm.py) ──────────────────────────────────────
    llm_backend: str = "gemini"  # gemini | groq | local | passages

    # Gemini (default — OpenAI-compatible endpoint) — tier 1
    gemini_api_key: str = ""  # secret
    gemini_model: str = "gemini-2.0-flash"
    gemini_max_tokens: int = 4096
    gemini_temperature: float = 0.3

    # Groq (free tier, OpenAI-compatible) — tier 2 (fallback)
    groq_api_key: str = ""  # secret
    groq_model: str = "llama-3.3-70b-versatile"
    groq_max_tokens: int = 4096
    groq_temperature: float = 0.3

    # Local model fallback (env names are LLM_*)
    llm_model: str = "Qwen/Qwen3-8B"
    llm_context_window: int = 8192
    llm_max_tokens: int = 512
    llm_temperature: float = 0.2
    llm_device: str = "auto"
    gguf_model_path: str = ""  # set to enable the GGUF/llama-cpp tier
    local_gpu_layers: int = 0
    lora_adapter_path: str = ""

    # ── Retrieval / indexing (retriever.py, indexer.py) ─────────────────────
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "musawo_health_kb"
    dense_model: str = "BAAI/bge-m3"
    dense_dim: int = 1024
    reranker_model: str = "mixedbread-ai/mxbai-rerank-base-v2"
    rerank_enabled: bool = True
    bm25_state_path: str = "knowledge-base/bm25_state.json"
    prefetch_limit: int = 20
    # canonical knowledge-base dir (replaces the legacy KB_DIR env var)
    knowledge_base_dir: str = "knowledge-base"
    chunk_size: int = 600
    chunk_overlap: int = 100
    index_batch_size: int = 64

    # ── Semantic cache (cache.py) ───────────────────────────────────────────
    cache_backend: str = "memory"  # memory | redis
    cache_enabled: bool = True
    cache_threshold: float = 0.92
    cache_ttl_seconds: int = 3600
    cache_max_size: int = 1000
    redis_url: str = "redis://localhost:6379/0"
    cache_redis_prefix: str = "musawo:cache:"

    # ── Corrective RAG (corrective_rag.py) ──────────────────────────────────
    corrective_rag_enabled: bool = True
    corrective_rag_threshold: float = 0.3

    # ── Guardrails + service (guardrails.py, service.py) ────────────────────
    max_input_length: int = 2000
    abstention_threshold: float = 0.05
    escalation_threshold: float = 0.25
    grounding_threshold: float = 0.3
    clinical_safety_threshold: float = 0.2
    llm_inference_timeout: int = 45
    session_ttl_seconds: int = 86400
    llm_workers: int = 2
    audit_log_path: str = "/tmp/musawo_audit.jsonl"

    # ── Sunbird voice/translation (sunbird.py) ──────────────────────────────
    sunbird_api_url: str = "https://api.sunbird.ai"
    sunbird_timeout: int = 30
    sunbird_api_token: str = ""  # secret — static fallback
    sunbird_username: str = ""  # secret — preferred (auto-refreshing token)
    sunbird_password: str = ""  # secret
    sunbird_fallback_username: str = ""  # secret
    sunbird_fallback_password: str = ""  # secret
    cosyvoice_model: str = "iic/CosyVoice2-0.5B"

    # ── Twilio SMS (sms_gateway.py) ─────────────────────────────────────────
    twilio_account_sid: str = ""  # secret
    twilio_auth_token: str = ""  # secret
    twilio_phone_number: str = ""

    # ── Voice VAD (voice_stream.py) ─────────────────────────────────────────
    voice_silero_enabled: bool = True
    voice_vad_energy_threshold: float = 0.015
    voice_vad_silence_ms: int = 600
    voice_vad_min_speech_ms: int = 250
    voice_vad_max_utterance_s: float = 30.0


settings = Settings()
"""Process-wide settings singleton. Import this, not the class."""
