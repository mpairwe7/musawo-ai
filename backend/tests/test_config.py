"""Tests for the centralized pydantic-settings configuration (app.config).

Guards:
- critical defaults match the values the code relied on before centralization
- env overrides are coerced to the right types
- unknown env keys (fork/PaaS leftovers) never crash boot
- .env.example holds no real-secret-shaped values and covers every Settings field
"""

import re
from pathlib import Path

from app.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"

# Patterns that indicate a REAL secret accidentally committed to .env.example
SECRET_PATTERNS = [r"gsk_[A-Za-z0-9]{8}", r"sk-ant-", r"AC[0-9a-f]{32}", r"hf_[A-Za-z0-9]{8}"]

# Keys cleared before building a "clean" Settings so process env can't skew defaults
_CLEARED = [
    "ABSTENTION_THRESHOLD", "ESCALATION_THRESHOLD", "GROUNDING_THRESHOLD",
    "CLINICAL_SAFETY_THRESHOLD", "MAX_INPUT_LENGTH", "GROQ_MAX_TOKENS",
    "CLAUDE_PROMPT_CACHING", "LLM_BACKEND", "CACHE_REDIS_PREFIX",
    "MAX_AUDIO_SIZE", "RERANK_ENABLED", "CLAUDE_TEMPERATURE",
]


def _clean_settings(monkeypatch, **overrides):
    """Build Settings ignoring the repo .env file and a curated set of process env."""
    for key in _CLEARED:
        monkeypatch.delenv(key, raising=False)
    for k, v in overrides.items():
        monkeypatch.setenv(k, v)
    return Settings(_env_file=None)


class TestConfigDefaults:
    def test_critical_defaults_match_code(self, monkeypatch):
        s = _clean_settings(monkeypatch)
        assert s.abstention_threshold == 0.05  # per CLAUDE.md, lowered from 0.15
        assert s.escalation_threshold == 0.25
        assert s.grounding_threshold == 0.3
        assert s.clinical_safety_threshold == 0.2
        assert s.max_input_length == 2000
        assert s.groq_max_tokens == 4096
        assert s.claude_prompt_caching is True
        assert s.llm_backend == "groq"
        assert s.max_audio_size == 10 * 1024 * 1024

    def test_fork_leftover_prefix_fixed(self, monkeypatch):
        # was "ura:cache:" in the URA fork — must now be the Musawo namespace
        s = _clean_settings(monkeypatch)
        assert s.cache_redis_prefix == "musawo:cache:"


class TestConfigTypes:
    def test_env_overrides_coerce_types(self, monkeypatch):
        s = _clean_settings(
            monkeypatch,
            GROQ_MAX_TOKENS="256",
            RERANK_ENABLED="false",
            CLAUDE_TEMPERATURE="0.7",
        )
        assert s.groq_max_tokens == 256 and isinstance(s.groq_max_tokens, int)
        assert s.rerank_enabled is False
        assert s.claude_temperature == 0.7 and isinstance(s.claude_temperature, float)


class TestConfigResilience:
    def test_unknown_env_keys_ignored(self, monkeypatch):
        # the real .env may carry fork/PaaS leftovers — they must never crash boot
        monkeypatch.setenv("AGRILINK_GROQ_API_KEY", "x")
        monkeypatch.setenv("CRANE_CLOUD_PASSWORD", "y")
        s = Settings(_env_file=None)  # must not raise
        assert s.llm_backend  # sanity: object built


class TestEnvExample:
    def test_no_real_secrets_in_example(self):
        text = ENV_EXAMPLE.read_text()
        for pat in SECRET_PATTERNS:
            assert not re.search(pat, text), f"possible real secret matching /{pat}/ in .env.example"

    def test_example_covers_every_settings_field(self):
        keys = set(re.findall(r"^([A-Z][A-Z0-9_]+)=", ENV_EXAMPLE.read_text(), re.M))
        missing = [name.upper() for name in Settings.model_fields if name.upper() not in keys]
        assert not missing, f".env.example is missing keys for Settings fields: {missing}"
