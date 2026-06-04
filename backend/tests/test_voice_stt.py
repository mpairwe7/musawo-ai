"""Tests for English STT via Cloudflare Workers AI Whisper (egress-safe on RENU)."""

import app.sunbird as sb


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


class TestCloudflareWhisperSTT:
    def test_success_returns_text(self, monkeypatch):
        monkeypatch.setattr(sb, "CF_ACCOUNT_ID", "acct")
        monkeypatch.setattr(sb, "CF_API_TOKEN", "tok")
        monkeypatch.setattr(sb, "CF_STT_MODEL", "@cf/openai/whisper-large-v3-turbo")
        seen = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            seen["url"] = url
            seen["headers"] = headers
            seen["json"] = json
            return _Resp({"success": True, "result": {"text": "Take ORS and zinc."}})

        monkeypatch.setattr(sb.httpx, "post", fake_post)
        out = sb._cloudflare_whisper_stt(b"\x00\x01raw-audio")
        assert out and out["text"] == "Take ORS and zinc."
        assert out["backend"] == "cloudflare-whisper"
        assert "ai/run/@cf/openai/whisper-large-v3-turbo" in seen["url"]
        assert seen["headers"]["Authorization"] == "Bearer tok"
        assert "audio" in seen["json"]  # base64-encoded audio in the body

    def test_unconfigured_returns_none(self, monkeypatch):
        monkeypatch.setattr(sb, "CF_ACCOUNT_ID", "")
        monkeypatch.setattr(sb, "CF_API_TOKEN", "")
        assert sb._cloudflare_whisper_stt(b"x") is None

    def test_api_failure_returns_none(self, monkeypatch):
        monkeypatch.setattr(sb, "CF_ACCOUNT_ID", "acct")
        monkeypatch.setattr(sb, "CF_API_TOKEN", "tok")
        monkeypatch.setattr(
            sb.httpx, "post", lambda *a, **k: _Resp({"success": False, "errors": ["nope"]})
        )
        assert sb._cloudflare_whisper_stt(b"x") is None

    def test_english_prefers_cloudflare_over_openai(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            sb,
            "_cloudflare_whisper_stt",
            lambda b: calls.append("cf")
            or {"text": "hello", "language": "eng", "backend": "cloudflare-whisper"},
        )
        monkeypatch.setattr(sb, "OPENAI_API_KEY", "sk-x")
        monkeypatch.setattr(sb, "_openai_whisper_stt", lambda b, f="audio.wav": calls.append("openai") or None)
        out = sb.speech_to_text(b"audio", language="en")
        assert out["backend"] == "cloudflare-whisper"
        assert calls == ["cf"]  # Cloudflare tried first; OpenAI never reached


class TestCloudflareMeloTTS:
    def test_success_returns_playable_data_url(self, monkeypatch):
        monkeypatch.setattr(sb, "CF_ACCOUNT_ID", "acct")
        monkeypatch.setattr(sb, "CF_API_TOKEN", "tok")
        monkeypatch.setattr(sb, "CF_TTS_MODEL", "@cf/myshell-ai/melotts")
        seen = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            seen["url"] = url
            seen["json"] = json
            return _Resp({"success": True, "result": {"audio": "QUJD"}})  # base64 "ABC"

        monkeypatch.setattr(sb.httpx, "post", fake_post)
        out = sb._cloudflare_melotts("Take ORS and zinc.")
        assert out and out["backend"] == "cloudflare-melotts"
        assert out["audio_url"] == "data:audio/mpeg;base64,QUJD"
        assert "melotts" in seen["url"]
        assert seen["json"]["lang"] == "en"

    def test_unconfigured_returns_none(self, monkeypatch):
        monkeypatch.setattr(sb, "CF_ACCOUNT_ID", "")
        monkeypatch.setattr(sb, "CF_API_TOKEN", "")
        assert sb._cloudflare_melotts("hi") is None

    def test_english_tts_prefers_cloudflare(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            sb,
            "_cloudflare_melotts",
            lambda t: calls.append("cf") or {"audio_url": "data:audio/mpeg;base64,QUJD", "backend": "cloudflare-melotts"},
        )
        monkeypatch.setattr(sb, "_local_tts_fallback", lambda t, l: calls.append("local") or None)
        out = sb.text_to_speech("hello", locale="en")
        assert out["backend"] == "cloudflare-melotts"
        assert calls == ["cf"]  # Cloudflare tried first; local fallback never reached
