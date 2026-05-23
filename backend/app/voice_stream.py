"""Portable streaming voice engine — Hybrid VAD, sentence-chunked TTS, barge-in.

2026 v2.6 upgrade: Hybrid VAD (energy gate + Silero ONNX neural confirmation),
noise gate preprocessing, prosody-aware TTS, semantic endpointing.

Architecture::

    Client PCM chunks ──▶ Energy gate ──▶ Silero confirm ──▶ utterance buffer
                                                                     │
                                                                     ▼
                    Noise gate ──▶ ASR (Sunbird) ──▶ [MT] ──▶ LLM ──▶ [MT] ──▶ TTS
                                                                                  │
                                  ◄── prosody-hinted sentence chunks ◄───────────┘
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import pathlib
import re
import struct
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Silero VAD — Neural speech confirmation (1.6MB ONNX, <1ms/frame on CPU)
# ---------------------------------------------------------------------------

_SILERO_ENABLED = os.getenv("VOICE_SILERO_ENABLED", "true").lower() in ("true", "1", "yes")
_SILERO_MODEL_URL = (
    "https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx"
)
_SILERO_CACHE_DIR = pathlib.Path.home() / ".cache" / "silero_vad"


class SileroVAD:
    """Lightweight neural VAD using Silero ONNX model.

    Runs in <1ms per frame on CPU. Only invoked when energy gate fires,
    so zero cost on silent frames.
    """

    def __init__(self, sample_rate: int = 16000):
        self._session = None
        self._sr = sample_rate
        # Internal RNN state (Silero requires h/c across frames)
        self._h = np.zeros((2, 1, 64), dtype=np.float32)
        self._c = np.zeros((2, 1, 64), dtype=np.float32)
        self._load_model()

    def _load_model(self) -> None:
        """Load ONNX model, downloading if needed."""
        try:
            import onnxruntime as ort
        except ImportError:
            logger.warning("onnxruntime not installed — Silero VAD disabled")
            return

        model_path = _SILERO_CACHE_DIR / "silero_vad.onnx"
        if not model_path.exists():
            logger.info("Downloading Silero VAD model (1.6MB)...")
            _SILERO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            try:
                import urllib.request
                urllib.request.urlretrieve(_SILERO_MODEL_URL, str(model_path))
                logger.info("Silero VAD model cached at %s", model_path)
            except Exception as e:
                logger.warning("Failed to download Silero VAD: %s", e)
                return

        try:
            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 1
            opts.intra_op_num_threads = 1
            self._session = ort.InferenceSession(str(model_path), opts)
            logger.info("Silero VAD loaded (ONNX Runtime)")
        except Exception as e:
            logger.warning("Failed to load Silero VAD: %s", e)
            self._session = None

    def __call__(self, pcm16_bytes: bytes) -> float:
        """Return speech probability [0.0, 1.0] for a PCM16 audio frame."""
        if self._session is None:
            return 1.0  # If unavailable, don't block — let energy VAD decide

        # Convert PCM16 LE to float32 [-1, 1]
        n_samples = len(pcm16_bytes) // 2
        if n_samples == 0:
            return 0.0
        samples = np.frombuffer(pcm16_bytes[:n_samples * 2], dtype=np.int16)
        audio = samples.astype(np.float32) / 32768.0
        audio = audio.reshape(1, -1)

        sr = np.array(self._sr, dtype=np.int64)

        try:
            out, self._h, self._c = self._session.run(
                None,
                {"input": audio, "sr": sr, "h": self._h, "c": self._c},
            )
            return float(out.squeeze())
        except Exception as e:
            logger.warning("Silero VAD inference failed: %s", e)
            return 1.0  # Fail open

    def reset(self) -> None:
        """Clear RNN hidden states between utterances."""
        self._h = np.zeros((2, 1, 64), dtype=np.float32)
        self._c = np.zeros((2, 1, 64), dtype=np.float32)

    @property
    def is_available(self) -> bool:
        return self._session is not None

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
    """Configurable VAD thresholds — hybrid energy + Silero."""

    energy_threshold: float = _VAD_ENERGY_THRESHOLD
    silence_duration_ms: int = _VAD_SILENCE_MS
    min_speech_duration_ms: int = _VAD_MIN_SPEECH_MS
    max_utterance_s: float = _VAD_MAX_UTTERANCE_S
    sample_rate: int = 16_000
    silero_enabled: bool = _SILERO_ENABLED
    silero_threshold: float = 0.5

    @classmethod
    def from_sensitivity(cls, sensitivity: str = "medium", sr: int = 16_000) -> VADConfig:
        presets = {
            "low": cls(  # Noisy environments — stricter confirmation
                energy_threshold=0.025, silence_duration_ms=800,
                silero_threshold=0.6, sample_rate=sr,
            ),
            "medium": cls(  # Default
                energy_threshold=0.015, silence_duration_ms=600,
                silero_threshold=0.5, sample_rate=sr,
            ),
            "high": cls(  # Quiet rooms — sensitive
                energy_threshold=0.008, silence_duration_ms=400,
                silero_threshold=0.35, sample_rate=sr,
            ),
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


def _noise_gate(pcm16_bytes: bytes, threshold: float = 0.008) -> bytes:
    """Zero out PCM16 frames below noise floor — cleans audio before STT.

    Complements browser-side noiseSuppression by hard-gating residual noise.
    """
    if len(pcm16_bytes) < 4:
        return pcm16_bytes
    frame_size = 640  # 20ms at 16kHz (320 samples × 2 bytes)
    output = bytearray()
    for i in range(0, len(pcm16_bytes), frame_size):
        frame = pcm16_bytes[i:i + frame_size]
        energy = _compute_energy(frame)
        if energy >= threshold:
            output.extend(frame)
        else:
            output.extend(b"\x00" * len(frame))
    return bytes(output)


# ---------------------------------------------------------------------------
# Semantic endpointing — detect natural turn completions
# ---------------------------------------------------------------------------

_ENDPOINT_PHRASES = {
    # English
    "that's all", "that is all", "help me", "thank you", "thanks",
    # Luganda
    "ekyo kyokka", "nkyo", "basi", "webale", "nkusaba",
    # Runyankole
    "nikyo", "wabure",
    # Swahili
    "hiyo tu", "asante", "tafadhali",
}


def _check_semantic_endpoint(transcript: str) -> bool:
    """Check if transcript indicates user has finished speaking."""
    if not transcript:
        return False
    text = transcript.strip().lower()
    # Ends with question mark
    if text.endswith("?"):
        return True
    # Ends with known completion phrase
    for phrase in _ENDPOINT_PHRASES:
        if text.endswith(phrase):
            return True
    # Short single-sentence (<10 words) likely complete
    words = text.split()
    if len(words) <= 8 and not text.endswith(","):
        return True
    return False


# ---------------------------------------------------------------------------
# Prosody detection — emotion-aware TTS parameters
# ---------------------------------------------------------------------------

_URGENT_PATTERNS = re.compile(
    r"refer\s+(now|immediately)|danger\s+sign|emergency|life.?threatening|"
    r"call\s+0800|obubonero\s+bw.akabi|hatari",
    re.IGNORECASE,
)


def _detect_prosody(
    text: str, triage_severity: str | None = None
) -> dict[str, float]:
    """Determine TTS rate/pitch based on clinical urgency."""
    if triage_severity == "red" or _URGENT_PATTERNS.search(text):
        return {"rate": 1.1, "pitch": 1.15, "urgency": "high"}
    if triage_severity == "yellow":
        return {"rate": 1.0, "pitch": 1.05, "urgency": "medium"}
    return {"rate": 0.95, "pitch": 1.0, "urgency": "normal"}


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

        # Hybrid VAD: energy gate + Silero neural confirmation
        self._silero_vad: SileroVAD | None = None
        if self.vad.silero_enabled:
            try:
                self._silero_vad = SileroVAD(sample_rate=self.vad.sample_rate)
                if not self._silero_vad.is_available:
                    self._silero_vad = None
            except Exception as e:
                logger.warning("Silero VAD init failed, using energy-only: %s", e)

        # VAD state
        self._speaking = False
        self._silence_start: float | None = None
        self._speech_start: float | None = None
        self._audio_buffer = bytearray()

        # Barge-in
        self._barge_in = asyncio.Event()
        self._tts_playing = False

    def feed_audio(self, pcm16: bytes, partial_transcript: str | None = None) -> VoiceEvent | None:
        """Feed a PCM16 audio chunk. Returns VoiceEvent if VAD state changes.

        Hybrid VAD: energy gate → Silero neural confirmation.
        Energy remains the fast gate (no neural inference on silent frames).
        Silero confirms only when energy suggests speech.
        """
        energy = _compute_energy(pcm16)
        now = time.time()

        # Hybrid decision: energy gate + optional Silero confirmation
        is_speech = energy >= self.vad.energy_threshold
        if is_speech and self._silero_vad is not None:
            silero_prob = self._silero_vad(pcm16)
            if silero_prob < self.vad.silero_threshold:
                is_speech = False  # Energy detected but Silero says noise

        if is_speech:
            # Speech detected (confirmed by both energy + Silero)
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
                else:
                    silence_ms = (now - self._silence_start) * 1000
                    # Semantic endpointing: shorter silence if turn is clearly complete
                    endpoint_threshold = self.vad.silence_duration_ms
                    if partial_transcript and _check_semantic_endpoint(partial_transcript):
                        endpoint_threshold = min(200, endpoint_threshold)

                    if silence_ms >= endpoint_threshold:
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
        """Return accumulated audio buffer, apply noise gate, and clear."""
        audio = _noise_gate(bytes(self._audio_buffer))
        self._audio_buffer.clear()
        if self._silero_vad is not None:
            self._silero_vad.reset()
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

        # 5. Prosody detection + Sentence-chunked TTS
        triage_sev = result.get("triage", {}).get("severity") if isinstance(result, dict) else None
        prosody = _detect_prosody(answer, triage_sev)
        yield VoiceEvent("prosody_hint", prosody)

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