"""Portable streaming voice engine — VAD, sentence-chunked TTS, barge-in.

Lightweight adaptation of the URA Chatbot voice pipeline for deployment on
Crane Cloud without GPU dependencies. Uses Sunbird AI for cloud STT/TTS
and energy-based VAD (no silero-vad needed).

Architecture::

    Client PCM chunks ──▶ VAD ──▶ utterance buffer
                                       │
                                       ▼  (utterance complete)
                           ASR (Sunbird) ──▶ [MT] ──▶ LLM (Groq) ──▶ [MT] ──▶ TTS
                                                                                 │
                           ◄── sentence chunks ◄─────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import re
import struct
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_VAD_ENERGY_THRESHOLD = float(os.getenv("VOICE_VAD_ENERGY_THRESHOLD", "0.015"))
_VAD_SILENCE_MS = int(os.getenv("VOICE_VAD_SILENCE_MS", "600"))
_VAD_MIN_SPEECH_MS = int(os.getenv("VOICE_VAD_MIN_SPEECH_MS", "250"))
_VAD_MAX_UTTERANCE_S = float(os.getenv("VOICE_VAD_MAX_UTTERANCE_S", "30.0"))
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class VADConfig:
    """Configurable VAD thresholds."""

    energy_threshold: float = _VAD_ENERGY_THRESHOLD
    silence_duration_ms: int = _VAD_SILENCE_MS
    min_speech_duration_ms: int = _VAD_MIN_SPEECH_MS
    max_utterance_s: float = _VAD_MAX_UTTERANCE_S
    sample_rate: int = 16_000

    @classmethod
    def from_sensitivity(cls, sensitivity: str = "medium", sr: int = 16_000) -> VADConfig:
        presets = {
            "low": cls(energy_threshold=0.025, silence_duration_ms=800, sample_rate=sr),
            "medium": cls(energy_threshold=0.015, silence_duration_ms=600, sample_rate=sr),
            "high": cls(energy_threshold=0.008, silence_duration_ms=400, sample_rate=sr),
        }
        return presets.get(sensitivity, presets["medium"])


@dataclass
class VoiceEvent:
    """Wire-format event for WebSocket."""

    type: str
    data: dict[str, Any] = field(default_factory=dict)


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, handling abbreviations."""
    abbrevs = {"mr.", "mrs.", "dr.", "prof.", "sr.", "jr.", "vs.", "etc.", "e.g.", "i.e."}
    protected = text
    for a in abbrevs:
        protected = protected.replace(a, a.replace(".", "<DOT>"))
    parts = _SENTENCE_RE.split(protected)
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]


def _compute_energy(pcm16_bytes: bytes) -> float:
    """RMS energy of PCM16 LE audio frame."""
    if len(pcm16_bytes) < 4:
        return 0.0
    n_samples = len(pcm16_bytes) // 2
    samples = struct.unpack(f"<{n_samples}h", pcm16_bytes[:n_samples * 2])
    rms = math.sqrt(sum(s * s for s in samples) / n_samples) / 32768.0
    return rms


class VoiceSession:
    """One streaming voice conversation. Manages VAD, ASR, LLM, TTS pipeline."""

    def __init__(
        self,
        session_id: str,
        sunbird_module: Any,
        generate_fn: Any,
        vad_config: VADConfig | None = None,
        language: str = "en",
        tts_enabled: bool = True,
    ):
        self.session_id = session_id
        self.sunbird = sunbird_module
        self.generate_fn = generate_fn  # App's service.generate() or equivalent
        self.vad = vad_config or VADConfig()
        self.language = language
        self.tts_enabled = tts_enabled

        # VAD state
        self._speaking = False
        self._silence_start: float | None = None
        self._speech_start: float | None = None
        self._audio_buffer = bytearray()

        # Barge-in
        self._barge_in = asyncio.Event()
        self._tts_playing = False

    def feed_audio(self, pcm16: bytes) -> VoiceEvent | None:
        """Feed a PCM16 audio chunk. Returns VoiceEvent if VAD state changes."""
        energy = _compute_energy(pcm16)
        now = time.time()

        if energy >= self.vad.energy_threshold:
            # Speech detected
            if not self._speaking:
                self._speaking = True
                self._speech_start = now
                self._silence_start = None
                self._audio_buffer.clear()
                return VoiceEvent("vad_state", {"speaking": True})
            self._silence_start = None
            self._audio_buffer.extend(pcm16)
        else:
            # Silence
            if self._speaking:
                self._audio_buffer.extend(pcm16)
                if self._silence_start is None:
                    self._silence_start = now
                elif (now - self._silence_start) * 1000 >= self.vad.silence_duration_ms:
                    # Utterance complete
                    speech_dur = (now - (self._speech_start or now)) * 1000
                    if speech_dur >= self.vad.min_speech_duration_ms:
                        self._speaking = False
                        return VoiceEvent("vad_state", {"speaking": False, "utterance_ready": True})
                    else:
                        self._speaking = False
                        self._audio_buffer.clear()
                        return VoiceEvent("vad_state", {"speaking": False, "too_short": True})

        # Max utterance guard
        if self._speaking and self._speech_start and (now - self._speech_start) >= self.vad.max_utterance_s:
            self._speaking = False
            return VoiceEvent("vad_state", {"speaking": False, "utterance_ready": True, "max_reached": True})

        return None

    def get_utterance_audio(self) -> bytes:
        """Return accumulated audio buffer and clear it."""
        audio = bytes(self._audio_buffer)
        self._audio_buffer.clear()
        return audio

    def barge_in(self) -> None:
        """Interrupt TTS playback."""
        self._barge_in.set()

    async def process_utterance(self, audio: bytes) -> AsyncGenerator[VoiceEvent, None]:
        """Full pipeline: ASR → [MT] → LLM → [MT] → sentence-chunked TTS."""
        t0 = time.time()
        self._barge_in.clear()

        # 1. ASR
        t_asr = time.time()
        transcript = await asyncio.get_event_loop().run_in_executor(
            None, self._do_asr, audio
        )
        asr_ms = (time.time() - t_asr) * 1000

        if not transcript:
            yield VoiceEvent("error", {"detail": "ASR returned empty", "recoverable": True})
            return

        yield VoiceEvent("transcript_final", {
            "text": transcript,
            "language": self.language,
            "latency_s": round(asr_ms / 1000, 3),
        })

        # 2. Translate to English if needed
        t_mt = time.time()
        query = transcript
        if self.language != "en":
            translated = await asyncio.get_event_loop().run_in_executor(
                None, self._translate_to_en, transcript
            )
            if translated:
                query = translated
        mt_in_ms = (time.time() - t_mt) * 1000

        # 3. LLM generation
        t_llm = time.time()
        result = await asyncio.get_event_loop().run_in_executor(
            None, self.generate_fn, query
        )
        llm_ms = (time.time() - t_llm) * 1000

        answer = result.get("answer", "") if isinstance(result, dict) else str(result)

        # 4. Translate back if needed
        t_mt_out = time.time()
        spoken_text = answer
        if self.language != "en":
            translated_back = await asyncio.get_event_loop().run_in_executor(
                None, self._translate_from_en, answer
            )
            if translated_back:
                spoken_text = translated_back
        mt_out_ms = (time.time() - t_mt_out) * 1000

        # 5. Sentence-chunked TTS
        sentences = _split_sentences(spoken_text)
        tts_first_ms = 0.0
        self._tts_playing = True

        for i, sentence in enumerate(sentences):
            if self._barge_in.is_set():
                yield VoiceEvent("reply_text", {"text": "[interrupted]", "chunk_index": i})
                break

            yield VoiceEvent("reply_text", {"text": sentence, "chunk_index": i})

            if self.tts_enabled:
                t_tts = time.time()
                tts_audio = await asyncio.get_event_loop().run_in_executor(
                    None, self._do_tts, sentence
                )
                if i == 0:
                    tts_first_ms = (time.time() - t_tts) * 1000

                if tts_audio and not self._barge_in.is_set():
                    yield VoiceEvent("audio_start", {"sample_rate": 24000})
                    yield VoiceEvent("audio_chunk", {"audio": tts_audio})
                    yield VoiceEvent("audio_end", {})

        self._tts_playing = False

        # 6. Latency report
        total_ms = (time.time() - t0) * 1000
        yield VoiceEvent("latency_report", {
            "asr_ms": round(asr_ms),
            "mt_in_ms": round(mt_in_ms),
            "llm_ms": round(llm_ms),
            "mt_out_ms": round(mt_out_ms),
            "tts_first_chunk_ms": round(tts_first_ms),
            "total_ms": round(total_ms),
        })

        # 7. Reply metadata
        sources = result.get("sources", []) if isinstance(result, dict) else []
        yield VoiceEvent("reply_meta", {
            "sources": sources,
            "confidence": result.get("confidence", 0) if isinstance(result, dict) else 0,
        })

    # -- Backend adapters (override per app) --

    def _do_asr(self, audio: bytes) -> str:
        """Speech-to-text via Sunbird."""
        try:
            result = self.sunbird.speech_to_text(audio, language=self.language)
            return result.get("text", "") if result else ""
        except Exception as e:
            logger.warning("ASR failed: %s", e)
            return ""

    def _do_tts(self, text: str) -> bytes | None:
        """Text-to-speech via Sunbird. Returns raw audio bytes or None."""
        try:
            result = self.sunbird.text_to_speech(text, locale=self.language)
            if result and result.get("audio_url"):
                import urllib.request
                with urllib.request.urlopen(result["audio_url"], timeout=10) as resp:
                    return resp.read()
            return None
        except Exception as e:
            logger.warning("TTS failed: %s", e)
            return None

    def _translate_to_en(self, text: str) -> str | None:
        try:
            return self.sunbird.translate_to_english(text, locale=self.language)
        except Exception:
            return None

    def _translate_from_en(self, text: str) -> str | None:
        try:
            return self.sunbird.translate_from_english(text, locale=self.language)
        except Exception:
            return None
