"""Regression tests for the LLM fallback chain (Gemini → Groq → local → passages).

Complements test_llm.py by exercising the demotion logic in generate() and
stream_tokens() directly, with each tier mocked so no network/model is needed.
The functions read the module-level GEMINI_API_KEY / GROQ_API_KEY globals, so we
monkeypatch those.
"""

from unittest.mock import patch

import pytest

import app.llm as llm

PASSAGES = [{"text": "Drink safe water and use ORS.", "source": "MoH", "section": "WASH"}]


@pytest.fixture(autouse=True)
def _keys_off_by_default(monkeypatch):
    # Default both providers OFF; each test opts in to the tiers it exercises.
    monkeypatch.setattr(llm, "GEMINI_API_KEY", "")
    monkeypatch.setattr(llm, "GROQ_API_KEY", "")


def _gen():
    return llm.generate("how to treat diarrhoea", PASSAGES, mode="community")


class TestGenerateFallback:
    def test_gemini_used_when_key_present(self, monkeypatch):
        monkeypatch.setattr(llm, "GEMINI_API_KEY", "gm_test")
        monkeypatch.setattr(llm, "GROQ_API_KEY", "gsk_test")
        with patch.object(llm, "generate_gemini", return_value={"text": "GEM", "usage": {}}) as gm, \
             patch.object(llm, "generate_groq") as g:
            assert _gen()["text"] == "GEM"
            gm.assert_called_once()
            g.assert_not_called()

    def test_gemini_failure_falls_to_groq(self, monkeypatch):
        monkeypatch.setattr(llm, "GEMINI_API_KEY", "gm_test")
        monkeypatch.setattr(llm, "GROQ_API_KEY", "gsk_test")
        with patch.object(llm, "generate_gemini", side_effect=RuntimeError("quota")), \
             patch.object(llm, "generate_groq", return_value={"text": "G", "usage": {}}) as g:
            assert _gen()["text"] == "G"
            g.assert_called_once()

    def test_groq_used_when_gemini_absent(self, monkeypatch):
        monkeypatch.setattr(llm, "GROQ_API_KEY", "gsk_test")
        with patch.object(llm, "generate_gemini") as gm, \
             patch.object(llm, "generate_groq", return_value={"text": "G", "usage": {}}) as g:
            assert _gen()["text"] == "G"
            gm.assert_not_called()
            g.assert_called_once()

    def test_all_apis_fail_falls_to_passages(self, monkeypatch):
        monkeypatch.setattr(llm, "GEMINI_API_KEY", "gm_test")
        monkeypatch.setattr(llm, "GROQ_API_KEY", "gsk_test")
        with patch.object(llm, "generate_gemini", side_effect=RuntimeError("x")), \
             patch.object(llm, "generate_groq", side_effect=RuntimeError("y")), \
             patch.object(llm, "generate_from_passages", return_value={"text": "P", "usage": {}}) as p:
            assert _gen()["text"] == "P"
            p.assert_called_once()

    def test_no_keys_uses_passages_directly(self, monkeypatch):
        monkeypatch.setattr(llm, "LLM_BACKEND", "passages")
        with patch.object(llm, "generate_gemini") as gm, \
             patch.object(llm, "generate_groq") as g, \
             patch.object(llm, "generate_from_passages", return_value={"text": "P", "usage": {}}) as p:
            assert _gen()["text"] == "P"
            gm.assert_not_called()
            g.assert_not_called()
            p.assert_called_once()


class TestStreamFallback:
    def test_gemini_stream_failure_falls_to_groq(self, monkeypatch):
        monkeypatch.setattr(llm, "GEMINI_API_KEY", "gm_test")
        monkeypatch.setattr(llm, "GROQ_API_KEY", "gsk_test")

        def _groq_stream(*a, **k):
            yield {"type": "token", "text": "G"}
            yield {"type": "done", "usage": {}}

        with patch.object(llm, "stream_gemini", side_effect=RuntimeError("stream fail")), \
             patch.object(llm, "stream_groq", side_effect=_groq_stream):
            chunks = list(llm.stream_tokens("q", PASSAGES))
        assert any(c.get("type") == "token" and c.get("text") == "G" for c in chunks)

    def test_stream_failure_falls_to_passages(self, monkeypatch):
        monkeypatch.setattr(llm, "GROQ_API_KEY", "gsk_test")
        monkeypatch.setattr(llm, "LLM_BACKEND", "passages")
        with patch.object(llm, "stream_groq", side_effect=RuntimeError("stream fail")), \
             patch.object(llm, "generate_from_passages",
                          return_value={"text": "P", "usage": {"total_tokens": 1}}):
            chunks = list(llm.stream_tokens("q", PASSAGES))
        assert any(c.get("type") == "token" and c.get("text") == "P" for c in chunks)
        assert chunks[-1]["type"] == "done"


class TestIsReady:
    def test_is_ready_true_without_keys_via_passage_tier(self, monkeypatch):
        # the passage tier is always available, so is_ready() must stay True
        monkeypatch.setattr(llm, "LLM_BACKEND", "passages")
        assert llm.is_ready() is True

    def test_is_ready_true_with_gemini(self, monkeypatch):
        monkeypatch.setattr(llm, "GEMINI_API_KEY", "gm_test")
        assert llm.is_ready() is True


class TestGeminiModelFallthrough:
    def test_unavailable_model_falls_through_to_next(self, monkeypatch):
        from unittest.mock import MagicMock
        monkeypatch.setattr(llm, "GEMINI_API_KEY", "gm_test")
        monkeypatch.setattr(llm, "GEMINI_VIA_GATEWAY", False)
        monkeypatch.setattr(llm, "GEMINI_MODELS", ["gemini-3.0-flash", "gemini-2.5-flash"])
        monkeypatch.setattr(llm, "_gemini_active_model", None)

        resp = MagicMock()
        resp.choices[0].message.content = "G25"
        resp.usage = None

        def _create(model, **kw):
            if "gemini-3.0-flash" in model:  # not yet available → 404
                raise RuntimeError("404 NOT_FOUND: model is not available")
            return resp

        client = MagicMock()
        client.chat.completions.create.side_effect = _create
        monkeypatch.setattr(llm, "_get_gemini_client", lambda: client)

        out = llm.generate_gemini("treat fever", PASSAGES, mode="community")
        assert out["text"] == "G25"
        assert llm._gemini_active_model == "gemini-2.5-flash"  # cached the working one

    def test_model_list_built_newest_first_with_fallback(self):
        # the live list prioritizes 3.x and always ends with a known-good model
        assert llm.GEMINI_MODELS[0].startswith("gemini-3")
        assert "gemini-2.5-flash" in llm.GEMINI_MODELS
        assert all(m not in llm._RETIRED_GEMINI for m in llm.GEMINI_MODELS)
