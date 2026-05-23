"""Musawo AI — Sunbird AI API integration.

Provides native Ugandan language support for:
- Translation (Luganda/Runyankole/Swahili ↔ English)
- Speech-to-Text (STT) with local language models
- Text-to-Speech (TTS) with native speaker voices
- Language auto-detection

API docs: https://docs.sunbird.ai
"""

from __future__ import annotations

import io
import logging
import os
from functools import lru_cache
from typing import Any

import httpx

logger = logging.getLogger("musawo.sunbird")

# ── Config ────────────────────────────────────────────────────────────────

SUNBIRD_API_URL = os.getenv("SUNBIRD_API_URL", "https://api.sunbird.ai")
SUNBIRD_TIMEOUT = int(os.getenv("SUNBIRD_TIMEOUT", "30"))

# Whisper Luganda LoRA adapter path — fine-tuned on 438hrs Luganda speech
WHISPER_LUGANDA_MODEL = os.getenv(
    "WHISPER_LUGANDA_MODEL",
    os.path.join(os.path.dirname(__file__), "../../../../fine-tuning/adapters/whisper-lg"),
)

# Auth credentials — primary + fallback (for token refresh & resilience)
SUNBIRD_API_TOKEN = os.getenv("SUNBIRD_API_TOKEN", "")
SUNBIRD_USERNAME = os.getenv("SUNBIRD_USERNAME", "")
SUNBIRD_PASSWORD = os.getenv("SUNBIRD_PASSWORD", "")

# Fallback credentials — used if primary auth fails
SUNBIRD_FALLBACK_USERNAME = os.getenv("SUNBIRD_FALLBACK_USERNAME", "")
SUNBIRD_FALLBACK_PASSWORD = os.getenv("SUNBIRD_FALLBACK_PASSWORD", "")

# Token refresh interval: refresh 1 day before expiry (tokens expire after 7 days)
_TOKEN_REFRESH_DAYS = 6

# Musawo locale → Sunbird language code mapping
LOCALE_TO_SUNBIRD: dict[str, str] = {
    "en": "eng",
    "lg": "lug",    # Luganda
    "nyn": "nyn",   # Runyankole
    "sw": "swa",    # Swahili (STT only — not available for translation)
}

# Sunbird TTS speaker IDs (native speakers)
TTS_SPEAKERS: dict[str, int] = {
    "lg": 248,    # Luganda female
    "nyn": 243,   # Runyankole female
    "sw": 246,    # Swahili male
}

# Languages supported for translation (Sunbird NLLB-based)
TRANSLATION_LANGUAGES = {"eng", "lug", "nyn", "ach", "teo", "lgg"}

# ── Auto-refreshing Token Manager ─────────────────────────────────────────

import time as _time
from threading import Lock as _Lock

_client: httpx.Client | None = None
_token_lock = _Lock()
_current_token: str = SUNBIRD_API_TOKEN
_token_obtained_at: float = 0.0  # epoch timestamp when token was obtained


def _try_auth(username: str, password: str, label: str) -> str | None:
    """Attempt auth with a single credential pair. Returns token or None."""
    try:
        resp = httpx.post(
            f"{SUNBIRD_API_URL}/auth/token",
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if token:
            logger.info("Sunbird token refreshed via %s account", label)
            return token
    except Exception as e:
        logger.warning("Sunbird %s auth failed: %s", label, e)
    return None


def _refresh_token() -> str | None:
    """Obtain a fresh access token. Tries primary credentials, then fallback.

    Auth chain:
    1. Primary credentials (SUNBIRD_USERNAME / SUNBIRD_PASSWORD)
    2. Fallback credentials (SUNBIRD_FALLBACK_USERNAME / SUNBIRD_FALLBACK_PASSWORD)

    This ensures resilience if one account hits rate limits, is suspended,
    or has an expired/changed password.
    """
    # Try primary credentials
    if SUNBIRD_USERNAME and SUNBIRD_PASSWORD:
        token = _try_auth(SUNBIRD_USERNAME, SUNBIRD_PASSWORD, "primary")
        if token:
            return token

    # Try fallback credentials
    if SUNBIRD_FALLBACK_USERNAME and SUNBIRD_FALLBACK_PASSWORD:
        token = _try_auth(SUNBIRD_FALLBACK_USERNAME, SUNBIRD_FALLBACK_PASSWORD, "fallback")
        if token:
            return token

    logger.error("All Sunbird auth attempts failed")
    return None


def _ensure_valid_token() -> str:
    """Return a valid token, refreshing proactively if near expiry.

    Token lifecycle:
    1. On first call: use SUNBIRD_API_TOKEN from env (if set)
    2. If credentials are configured: auto-refresh every 6 days
    3. On 401 error: force-refresh immediately
    """
    global _current_token, _token_obtained_at

    with _token_lock:
        now = _time.time()

        # If we have credentials and token is old (>6 days), refresh proactively
        if (SUNBIRD_USERNAME and SUNBIRD_PASSWORD and _token_obtained_at > 0
                and (now - _token_obtained_at) > _TOKEN_REFRESH_DAYS * 86400):
            logger.info("Sunbird token approaching expiry, refreshing proactively")
            new_token = _refresh_token()
            if new_token:
                _current_token = new_token
                _token_obtained_at = now
                # Recreate client with new token
                _rebuild_client(new_token)

        # If no token yet but credentials exist, get initial token
        if not _current_token and SUNBIRD_USERNAME and SUNBIRD_PASSWORD:
            new_token = _refresh_token()
            if new_token:
                _current_token = new_token
                _token_obtained_at = now

        return _current_token


def _rebuild_client(token: str) -> None:
    """Recreate the httpx client with a new bearer token."""
    global _client
    if _client:
        try:
            _client.close()
        except Exception:
            pass
    _client = httpx.Client(
        base_url=SUNBIRD_API_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=SUNBIRD_TIMEOUT,
    )


def _handle_401_refresh() -> bool:
    """Force-refresh token after receiving 401. Returns True if refreshed."""
    global _current_token, _token_obtained_at

    if not SUNBIRD_USERNAME or not SUNBIRD_PASSWORD:
        return False

    with _token_lock:
        logger.warning("Sunbird returned 401 — force-refreshing token")
        new_token = _refresh_token()
        if new_token:
            _current_token = new_token
            _token_obtained_at = _time.time()
            _rebuild_client(new_token)
            return True
    return False


def _get_client() -> httpx.Client:
    """Get httpx client with a valid auth token. Auto-refreshes if needed."""
    global _client, _token_obtained_at

    token = _ensure_valid_token()
    if not token:
        raise RuntimeError(
            "Sunbird API not configured. Set SUNBIRD_API_TOKEN or "
            "SUNBIRD_USERNAME + SUNBIRD_PASSWORD environment variables."
        )

    if _client is None:
        _token_obtained_at = _token_obtained_at or _time.time()
        _rebuild_client(token)
    return _client


def is_available() -> bool:
    """Check if Sunbird API is configured (token, primary, or fallback credentials)."""
    return bool(
        SUNBIRD_API_TOKEN
        or (SUNBIRD_USERNAME and SUNBIRD_PASSWORD)
        or (SUNBIRD_FALLBACK_USERNAME and SUNBIRD_FALLBACK_PASSWORD)
    )


# ── API call wrapper with auto-retry on 401 ─────────────────────────────

def _api_call(method: str, path: str, **kwargs: Any) -> httpx.Response:
    """Make a Sunbird API call with automatic 401 token refresh + retry.

    On 401 Unauthorized:
    1. Force-refresh the bearer token using stored credentials
    2. Retry the request once with the new token
    3. If still fails, raise the original error

    This ensures seamless operation across the 7-day token expiry window.
    """
    client = _get_client()
    resp = getattr(client, method)(path, **kwargs)

    if resp.status_code == 401:
        # Token expired — attempt refresh
        if _handle_401_refresh():
            client = _get_client()
            resp = getattr(client, method)(path, **kwargs)

    return resp


# ── Translation ───────────────────────────────────────────────────────────

def translate(text: str, source_lang: str, target_lang: str) -> str | None:
    """Translate text between languages.

    Args:
        text: Text to translate
        source_lang: Sunbird language code (eng, lug, nyn, etc.)
        target_lang: Sunbird language code

    Returns:
        Translated text, or None on failure.
    """
    if source_lang not in TRANSLATION_LANGUAGES or target_lang not in TRANSLATION_LANGUAGES:
        logger.warning("Translation not supported: %s → %s", source_lang, target_lang)
        return None

    try:
        resp = _api_call("post", "/tasks/translate", json={
            "source_language": source_lang,
            "target_language": target_lang,
            "text": text,
        })
        resp.raise_for_status()
        data = resp.json()
        result = data.get("output", {}).get("translated_text") or data.get("translated_text")
        if result:
            logger.info("Translated %s→%s: '%s' → '%s'", source_lang, target_lang,
                        text[:50], result[:50])
        return result
    except Exception as e:
        logger.warning("Sunbird translate failed: %s", e)
        return None


def translate_to_english(text: str, locale: str) -> str | None:
    """Translate from a Musawo locale to English for retrieval.

    Returns translated text, or None if locale is English or unsupported.
    """
    if locale == "en":
        return None
    src = LOCALE_TO_SUNBIRD.get(locale)
    if not src or src not in TRANSLATION_LANGUAGES:
        return None
    return translate(text, src, "eng")


def translate_from_english(text: str, locale: str) -> str | None:
    """Translate English text to the user's locale."""
    if locale == "en":
        return None
    tgt = LOCALE_TO_SUNBIRD.get(locale)
    if not tgt or tgt not in TRANSLATION_LANGUAGES:
        return None
    return translate(text, "eng", tgt)


# ── Speech-to-Text ────────────────────────────────────────────────────────

# Lazy-loaded local models (singleton pattern)
_parakeet_model = None
_cosyvoice_model = None


_whisper_lg_model = None

def _local_stt_fallback(audio_bytes: bytes, language: str) -> dict[str, Any] | None:
    """Local STT fallback chain: Whisper+LoRA → Parakeet TDT → Moonshine → Whisper.

    Priority:
    1. NVIDIA Parakeet TDT 0.6B — 5x realtime, best accuracy, ONNX support
    2. Moonshine — 27M params, 10x realtime, English-focused
    3. faster-whisper — ONNX Whisper, decent multilingual
    4. OpenAI Whisper — original, slowest

    All are Apache 2.0 / MIT licensed.
    """
    import tempfile

    # Save audio to temp file (most models need file path)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.write(audio_bytes)
    tmp.flush()
    tmp.close()
    audio_path = tmp.name

    # Strategy 0: Whisper + Luganda LoRA (fine-tuned, best for Luganda)
    lora_path = os.path.abspath(WHISPER_LUGANDA_MODEL)
    if os.path.isdir(lora_path) and os.path.exists(os.path.join(lora_path, "adapter_config.json")):
        try:
            global _whisper_lg_model
            if _whisper_lg_model is None:
                from transformers import WhisperForConditionalGeneration, WhisperProcessor
                from peft import PeftModel
                logger.info("Loading Whisper + Luganda LoRA from %s", lora_path)
                base_model = WhisperForConditionalGeneration.from_pretrained("openai/whisper-small")
                _whisper_lg_model = PeftModel.from_pretrained(base_model, lora_path)
                _whisper_lg_model.eval()
                _whisper_lg_model._processor = WhisperProcessor.from_pretrained("openai/whisper-small")
                logger.info("Whisper+LoRA Luganda model loaded")

            import soundfile as sf
            audio_array, sr = sf.read(audio_path)
            proc = _whisper_lg_model._processor
            inputs = proc(audio_array, sampling_rate=sr, return_tensors="pt")
            predicted_ids = _whisper_lg_model.generate(**inputs, max_new_tokens=225)
            text = proc.batch_decode(predicted_ids, skip_special_tokens=True)[0]
            logger.info("Whisper+LoRA STT (%s): '%s'", language, text[:80])
            return {"text": text, "language": language, "backend": "whisper-luganda-lora"}
        except ImportError:
            logger.debug("peft/transformers not available for Whisper+LoRA")
        except Exception as e:
            logger.warning("Whisper+LoRA STT failed: %s", e)

    # Strategy 1: NVIDIA Parakeet TDT 0.6B (best for production)
    # Install: pip install nemo_toolkit[asr]
    try:
        global _parakeet_model
        import nemo.collections.asr as nemo_asr

        if _parakeet_model is None:
            model_name = os.getenv(
                "PARAKEET_MODEL",
                "nvidia/parakeet-tdt-0.6b-v2",
            )
            logger.info("Loading Parakeet TDT model: %s", model_name)
            _parakeet_model = nemo_asr.models.ASRModel.from_pretrained(model_name)
            _parakeet_model.eval()

        transcriptions = _parakeet_model.transcribe([audio_path])
        text = transcriptions[0].text if hasattr(transcriptions[0], "text") else str(transcriptions[0])
        logger.info("Parakeet STT (%s): '%s'", language, text[:80])
        return {"text": text, "language": language, "backend": "parakeet-tdt"}
    except ImportError:
        logger.debug("nemo_toolkit not installed (pip install nemo_toolkit[asr])")
    except Exception as e:
        logger.warning("Parakeet STT failed: %s", e)

    # Strategy 2: Moonshine (ultra-lightweight, 27M params)
    # Install: pip install moonshine-onnx
    try:
        from moonshine_onnx import transcribe as moonshine_transcribe

        text = moonshine_transcribe(audio_path)
        if isinstance(text, list):
            text = " ".join(text)
        logger.info("Moonshine STT: '%s'", text[:80])
        return {"text": text, "language": language, "backend": "moonshine"}
    except ImportError:
        logger.debug("moonshine-onnx not installed (pip install moonshine-onnx)")
    except Exception as e:
        logger.warning("Moonshine STT failed: %s", e)

    # Strategy 3: faster-whisper (CTranslate2, ONNX-optimized Whisper)
    # Install: pip install faster-whisper
    try:
        from faster_whisper import WhisperModel

        model = WhisperModel("base", device="cpu", compute_type="int8")
        whisper_lang = {"lug": None, "nyn": None, "swa": "sw", "eng": "en"}.get(language)
        segments, _info = model.transcribe(audio_path, language=whisper_lang)
        text = " ".join(seg.text for seg in segments)
        logger.info("faster-whisper STT (%s): '%s'", language, text[:80])
        return {"text": text.strip(), "language": language, "backend": "faster-whisper"}
    except ImportError:
        logger.debug("faster-whisper not installed (pip install faster-whisper)")
    except Exception as e:
        logger.warning("faster-whisper STT failed: %s", e)

    # Strategy 4: OpenAI Whisper (original, heaviest)
    # Install: pip install openai-whisper
    try:
        import whisper

        model = whisper.load_model("base")
        whisper_lang = {"lug": None, "nyn": None, "swa": "sw", "eng": "en"}.get(language)
        result = model.transcribe(audio_path, language=whisper_lang)
        logger.info("Whisper STT (%s): '%s'", language, result["text"][:80])
        return {"text": result["text"], "language": language, "backend": "whisper"}
    except ImportError:
        logger.debug("openai-whisper not installed (pip install openai-whisper)")
    except Exception as e:
        logger.warning("Whisper STT failed: %s", e)

    # Clean up
    try:
        os.unlink(audio_path)
    except Exception:
        pass

    logger.error("All local STT backends failed. Install one of: "
                 "nemo_toolkit[asr], moonshine-onnx, faster-whisper, openai-whisper")
    return None


def speech_to_text(
    audio_bytes: bytes,
    language: str = "lug",
    filename: str = "audio.wav",
) -> dict[str, Any] | None:
    """Transcribe audio. Primary: Sunbird API. Fallback: Parakeet → Moonshine → Whisper.

    Args:
        audio_bytes: Raw audio file bytes (WAV, MP3, OGG, M4A, AAC)
        language: Sunbird language code (lug, nyn, swa, eng, etc.)
        filename: Original filename for MIME type detection

    Returns:
        Dict with 'text' and 'language', or None on failure.
    """
    # Primary: Sunbird API (best for Ugandan languages)
    if is_available():
        try:
            files = {"audio": (filename, io.BytesIO(audio_bytes))}
            data: dict[str, Any] = {}
            if language:
                data["language"] = language
            resp = _api_call("post", "/tasks/modal/stt", files=files, data=data)
            resp.raise_for_status()
            result = resp.json()
            transcription = (
                result.get("output", {}).get("audio_transcription")
                or result.get("audio_transcription", "")
            )
            logger.info("Sunbird STT (%s): '%s'", language, transcription[:80])
            return {
                "text": transcription,
                "language": result.get("language", language),
                "backend": "sunbird",
            }
        except Exception as e:
            logger.warning("Sunbird STT failed, trying local fallback: %s", e)

    # Fallback: local models (Parakeet → Moonshine → faster-whisper → Whisper)
    return _local_stt_fallback(audio_bytes, language)


# ── Text-to-Speech ────────────────────────────────────────────────────────

def _local_tts_fallback(text: str, locale: str) -> dict[str, Any] | None:
    """Local TTS fallback chain: CosyVoice2 → edge-tts.

    Priority:
    1. CosyVoice2-0.5B — fully offline, voice cloning, multilingual (Apache 2.0)
    2. edge-tts — Microsoft neural voices (needs internet, no API key)

    CosyVoice2 is preferred because:
    - Runs completely offline (critical for rural Uganda)
    - 500M params, fits in ~2GB RAM
    - Supports voice cloning from 3-second samples
    - Can be fine-tuned on Luganda/Runyankole speaker data
    """
    import tempfile

    # Strategy 1: CosyVoice2-0.5B (best for offline + local languages)
    # Install: git clone https://github.com/FunAudioLLM/CosyVoice.git + deps
    COSYVOICE_PATH = os.getenv(
        "COSYVOICE_PATH",
        os.path.join(os.path.dirname(__file__), "../../../CosyVoice"),
    )
    try:
        import sys
        if COSYVOICE_PATH not in sys.path:
            sys.path.insert(0, os.path.abspath(COSYVOICE_PATH))

        global _cosyvoice_model
        if _cosyvoice_model is None:
            from cosyvoice.cli.cosyvoice import CosyVoice
            model_name = os.getenv("COSYVOICE_MODEL", "iic/CosyVoice2-0.5B")
            logger.info("Loading CosyVoice model: %s", model_name)
            _cosyvoice_model = CosyVoice(model_name)

        # Generate speech — use SFT inference with default speaker
        output = _cosyvoice_model.inference_sft(text[:2000], speaker="default")

        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            import torchaudio
            torchaudio.save(f.name, output["tts_speech"], 22050)
            logger.info("CosyVoice TTS (%s): %s", locale, f.name)
            return {
                "audio_url": f"file://{f.name}",
                "file_name": f.name,
                "expires_at": None,
                "backend": "cosyvoice",
            }
    except ImportError:
        logger.debug("CosyVoice not found at %s", COSYVOICE_PATH)
    except Exception as e:
        logger.warning("CosyVoice TTS failed: %s", e)

    # Strategy 2: edge-tts (Microsoft neural voices, needs internet)
    # Install: pip install edge-tts
    try:
        import edge_tts
        import asyncio

        voice_map = {
            "lg": "en-UG-MaleNeural",    # Closest available voice
            "nyn": "en-UG-MaleNeural",
            "sw": "sw-KE-ZuriNeural",     # Native Swahili voice
            "en": "en-UG-MaleNeural",
        }
        voice = voice_map.get(locale, "en-UG-MaleNeural")

        async def _generate():
            communicate = edge_tts.Communicate(text[:2000], voice)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
                return f.name

        # Handle event loop — may already be running in async context
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                filepath = loop.run_in_executor(pool, lambda: asyncio.run(_generate()))
        except RuntimeError:
            filepath = asyncio.run(_generate())

        logger.info("edge-tts TTS (%s): %s", locale, filepath)
        return {
            "audio_url": f"file://{filepath}",
            "file_name": filepath,
            "expires_at": None,
            "backend": "edge-tts",
        }
    except ImportError:
        logger.debug("edge-tts not installed (pip install edge-tts)")
    except Exception as e:
        logger.warning("edge-tts TTS failed: %s", e)

    logger.error("All local TTS backends failed. Install one of: cosyvoice2, edge-tts")
    return None


def text_to_speech(
    text: str,
    locale: str = "lg",
    response_mode: str = "url",
) -> dict[str, Any] | None:
    """Convert text to speech. Primary: Sunbird. Fallback: edge-tts.

    Args:
        text: Text to speak (1-10000 chars)
        locale: Musawo locale code (lg, nyn, sw)
        response_mode: 'url' returns a signed URL, 'stream' returns audio bytes

    Returns:
        Dict with 'audio_url' and 'expires_at', or None on failure.
    """
    # Primary: Sunbird native voices
    speaker_id = TTS_SPEAKERS.get(locale)
    if is_available() and speaker_id:
        try:
            resp = _api_call("post", "/tasks/modal/tts", json={
                "text": text[:10000],
                "speaker_id": speaker_id,
                "response_mode": response_mode,
            })
            resp.raise_for_status()
            data = resp.json()
            audio_url = data.get("output", {}).get("audio_url") or data.get("audio_url")
            logger.info("Sunbird TTS (%s, speaker %d): url=%s", locale, speaker_id,
                         audio_url[:80] if audio_url else "none")
            return {
                "audio_url": audio_url,
                "file_name": data.get("file_name"),
                "expires_at": data.get("expires_at"),
            }
        except Exception as e:
            logger.warning("Sunbird TTS failed, trying local fallback: %s", e)

    # Fallback: local edge-tts
    return _local_tts_fallback(text, locale)


# ── Language Detection ────────────────────────────────────────────────────

# Sunbird code → Musawo locale mapping (reverse of LOCALE_TO_SUNBIRD)
_SUNBIRD_TO_LOCALE: dict[str, str] = {
    "eng": "en", "lug": "lg", "nyn": "nyn", "swa": "sw",
    "ach": "en", "teo": "en", "lgg": "en",  # fallback unsupported → English
}


def detect_language(text: str) -> dict[str, Any] | None:
    """Detect the language of input text.

    Returns:
        Dict with 'locale' (Musawo code) and 'sunbird_code' and 'confidence',
        or None on failure.
    """
    if len(text.strip()) < 3:
        return None

    try:
        resp = _api_call("post", "/tasks/language_id", json={"text": text[:200]})
        resp.raise_for_status()
        data = resp.json()
        lang_code = (
            data.get("output", {}).get("language")
            or data.get("language", "eng")
        )
        confidence = data.get("confidence", data.get("output", {}).get("confidence"))
        locale = _SUNBIRD_TO_LOCALE.get(lang_code, "en")
        logger.info("Language detected: %s → locale=%s (conf=%s)", lang_code, locale, confidence)
        return {
            "locale": locale,
            "sunbird_code": lang_code,
            "confidence": confidence,
        }
    except Exception as e:
        logger.warning("Sunbird language detection failed: %s", e)
        return None
