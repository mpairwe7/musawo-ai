"""Regression tests for the LLM fallback chain (Groq → Claude → passages).

Complements test_llm.py by exercising the demotion logic in generate() and
stream_tokens() directly, with each tier mocked so no network/model is needed.
The functions read the module-level GROQ_API_KEY / ANTHROPIC_API_KEY / LLM_BACKEND
globals, so we monkeypatch those.
"""

from unittest.mock import patch

import app.llm as llm

PASSAGES = [{"text": "Drink safe water and use ORS.", "source": "MoH", "section": "WASH"}]


def _gen():
    return llm.generate("how to treat diarrhoea", PASSAGES, mode="community")


class TestGenerateFallback:
    def test_groq_used_when_key_present(self, monkeypatch):
        monkeypatch.setattr(llm, "GROQ_API_KEY", "gsk_test")
        monkeypatch.setattr(llm, "ANTHROPIC_API_KEY", "")
        with patch.object(llm, "generate_groq", return_value={"text": "G", "usage": {}}) as g:
            assert _gen()["text"] == "G"
            g.assert_called_once()

    def test_groq_failure_falls_to_claude(self, monkeypatch):
        monkeypatch.setattr(llm, "GROQ_API_KEY", "gsk_test")
        monkeypatch.setattr(llm, "ANTHROPIC_API_KEY", "sk-ant-test")
        with patch.object(llm, "generate_groq", side_effect=RuntimeError("rate limited")), \
             patch.object(llm, "generate_claude", return_value={"text": "C", "usage": {}}) as c:
            assert _gen()["text"] == "C"
            c.assert_called_once()

    def test_all_apis_fail_falls_to_passages(self, monkeypatch):
        monkeypatch.setattr(llm, "GROQ_API_KEY", "gsk_test")
        monkeypatch.setattr(llm, "ANTHROPIC_API_KEY", "sk-ant-test")
        with patch.object(llm, "generate_groq", side_effect=RuntimeError("x")), \
             patch.object(llm, "generate_claude", side_effect=RuntimeError("y")), \
             patch.object(llm, "generate_from_passages", return_value={"text": "P", "usage": {}}) as p:
            assert _gen()["text"] == "P"
            p.assert_called_once()

    def test_no_keys_uses_passages_directly(self, monkeypatch):
        monkeypatch.setattr(llm, "GROQ_API_KEY", "")
        monkeypatch.setattr(llm, "ANTHROPIC_API_KEY", "")
        monkeypatch.setattr(llm, "LLM_BACKEND", "groq")
        with patch.object(llm, "generate_groq") as g, \
             patch.object(llm, "generate_claude") as c, \
             patch.object(llm, "generate_from_passages", return_value={"text": "P", "usage": {}}) as p:
            assert _gen()["text"] == "P"
            g.assert_not_called()
            c.assert_not_called()
            p.assert_called_once()


class TestStreamFallback:
    def test_groq_stream_failure_falls_to_passages(self, monkeypatch):
        monkeypatch.setattr(llm, "GROQ_API_KEY", "gsk_test")
        monkeypatch.setattr(llm, "ANTHROPIC_API_KEY", "")
        monkeypatch.setattr(llm, "LLM_BACKEND", "groq")
        with patch.object(llm, "stream_groq", side_effect=RuntimeError("stream fail")), \
             patch.object(llm, "generate_from_passages",
                          return_value={"text": "P", "usage": {"total_tokens": 1}}):
            chunks = list(llm.stream_tokens("q", PASSAGES))
        assert any(c.get("type") == "token" and c.get("text") == "P" for c in chunks)
        assert chunks[-1]["type"] == "done"


class TestIsReady:
    def test_is_ready_true_without_keys_via_passage_tier(self, monkeypatch):
        # the passage tier is always available, so is_ready() must stay True
        monkeypatch.setattr(llm, "GROQ_API_KEY", "")
        monkeypatch.setattr(llm, "ANTHROPIC_API_KEY", "")
        monkeypatch.setattr(llm, "LLM_BACKEND", "passages")
        assert llm.is_ready() is True
