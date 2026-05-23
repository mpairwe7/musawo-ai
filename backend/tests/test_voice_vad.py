"""Tests for Hybrid VAD, noise gate, semantic endpointing, and prosody detection."""

import math
import struct

import pytest

from app.voice_stream import (
    VADConfig,
    VoiceEvent,
    VoiceSession,
    _check_semantic_endpoint,
    _compute_energy,
    _detect_prosody,
    _noise_gate,
    _split_sentences,
)


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_pcm16(frequency: float = 440.0, duration_ms: int = 20, amplitude: float = 0.5, sr: int = 16000) -> bytes:
    """Generate a sine wave as PCM16 LE bytes."""
    n_samples = int(sr * duration_ms / 1000)
    samples = []
    for i in range(n_samples):
        val = amplitude * math.sin(2 * math.pi * frequency * i / sr)
        samples.append(int(val * 32767))
    return struct.pack(f"<{n_samples}h", *samples)


def _make_silence(duration_ms: int = 20, sr: int = 16000) -> bytes:
    """Generate silence (zero samples) as PCM16 LE bytes."""
    n_samples = int(sr * duration_ms / 1000)
    return b"\x00\x00" * n_samples


# ── Energy computation ───────────────────────────────────────────────────

class TestComputeEnergy:
    def test_silence_has_zero_energy(self):
        assert _compute_energy(_make_silence()) == 0.0

    def test_loud_signal_has_high_energy(self):
        pcm = _make_pcm16(amplitude=0.8)
        energy = _compute_energy(pcm)
        assert energy > 0.3

    def test_quiet_signal_has_low_energy(self):
        pcm = _make_pcm16(amplitude=0.01)
        energy = _compute_energy(pcm)
        assert energy < 0.02

    def test_empty_bytes_returns_zero(self):
        assert _compute_energy(b"") == 0.0
        assert _compute_energy(b"\x00") == 0.0


# ── Noise gate ───────────────────────────────────────────────────────────

class TestNoiseGate:
    def test_silence_is_preserved_as_zeros(self):
        silence = _make_silence(duration_ms=40)
        gated = _noise_gate(silence)
        assert all(b == 0 for b in gated)

    def test_loud_signal_passes_through(self):
        pcm = _make_pcm16(amplitude=0.5, duration_ms=40)
        gated = _noise_gate(pcm)
        assert gated != b"\x00" * len(gated)

    def test_output_same_length_as_input(self):
        pcm = _make_pcm16(duration_ms=60)
        gated = _noise_gate(pcm)
        assert len(gated) == len(pcm)


# ── VADConfig ────────────────────────────────────────────────────────────

class TestVADConfig:
    def test_default_has_silero_enabled(self):
        config = VADConfig()
        assert config.silero_enabled is True
        assert config.silero_threshold == 0.5

    def test_sensitivity_presets(self):
        low = VADConfig.from_sensitivity("low")
        med = VADConfig.from_sensitivity("medium")
        high = VADConfig.from_sensitivity("high")
        # Low sensitivity = higher threshold (less sensitive)
        assert low.energy_threshold > med.energy_threshold > high.energy_threshold
        assert low.silero_threshold > med.silero_threshold > high.silero_threshold

    def test_unknown_sensitivity_defaults_to_medium(self):
        config = VADConfig.from_sensitivity("extreme")
        assert config.energy_threshold == 0.015


# ── VoiceSession energy-only VAD (Silero disabled) ───────────────────────

class TestVoiceSessionEnergyOnly:
    def _make_session(self, **kw):
        config = VADConfig(silero_enabled=False, **kw)
        return VoiceSession(
            session_id="test",
            sunbird_module=None,
            generate_fn=lambda q: {"answer": "test"},
            vad_config=config,
        )

    def test_silence_produces_no_event(self):
        session = self._make_session()
        event = session.feed_audio(_make_silence())
        assert event is None

    def test_speech_triggers_speaking_true(self):
        session = self._make_session(energy_threshold=0.01)
        event = session.feed_audio(_make_pcm16(amplitude=0.5))
        assert event is not None
        assert event.type == "vad_state"
        assert event.data["speaking"] is True

    def test_speech_then_silence_triggers_utterance_ready(self):
        session = self._make_session(
            energy_threshold=0.01,
            silence_duration_ms=20,
            min_speech_duration_ms=10,
        )
        # Start speech
        session.feed_audio(_make_pcm16(amplitude=0.5))
        # Continue speech for a bit
        session.feed_audio(_make_pcm16(amplitude=0.5))
        # Silence
        import time
        time.sleep(0.03)  # Exceed silence_duration_ms
        event = session.feed_audio(_make_silence())
        # May need more silence frames
        if event is None:
            time.sleep(0.03)
            event = session.feed_audio(_make_silence())
        assert event is not None
        assert event.data.get("utterance_ready") or event.data.get("too_short")

    def test_get_utterance_audio_clears_buffer(self):
        session = self._make_session(energy_threshold=0.01)
        session.feed_audio(_make_pcm16(amplitude=0.5))
        audio = session.get_utterance_audio()
        assert isinstance(audio, bytes)
        # Second call returns empty (noise-gated silence)
        audio2 = session.get_utterance_audio()
        assert len(audio2) == 0


# ── Semantic endpointing ─────────────────────────────────────────────────

class TestSemanticEndpointing:
    def test_question_mark_triggers_endpoint(self):
        assert _check_semantic_endpoint("What is ORS dosage?") is True

    def test_luganda_completion_triggers(self):
        assert _check_semantic_endpoint("ekyo kyokka") is True

    def test_swahili_completion_triggers(self):
        assert _check_semantic_endpoint("asante") is True

    def test_short_statement_triggers(self):
        assert _check_semantic_endpoint("child has fever") is True

    def test_long_incomplete_does_not_trigger(self):
        long_text = "the child has been having symptoms including " + ", ".join(["fever"] * 20)
        assert _check_semantic_endpoint(long_text) is False

    def test_empty_does_not_trigger(self):
        assert _check_semantic_endpoint("") is False


# ── Prosody detection ────────────────────────────────────────────────────

class TestProsodyDetection:
    def test_urgent_text_high_rate(self):
        prosody = _detect_prosody("REFER NOW to health facility", "red")
        assert prosody["rate"] > 1.0
        assert prosody["urgency"] == "high"

    def test_normal_text_slower_rate(self):
        prosody = _detect_prosody("Give ORS solution as needed.", None)
        assert prosody["rate"] < 1.0
        assert prosody["urgency"] == "normal"

    def test_yellow_severity(self):
        prosody = _detect_prosody("Monitor the child", "yellow")
        assert prosody["urgency"] == "medium"

    def test_danger_sign_in_text(self):
        prosody = _detect_prosody("This is a danger sign, act immediately", None)
        assert prosody["urgency"] == "high"


# ── Sentence splitting ───────────────────────────────────────────────────

class TestSentenceSplitting:
    def test_basic_split(self):
        result = _split_sentences("Hello. World.")
        assert len(result) == 2

    def test_abbreviations_preserved(self):
        result = _split_sentences("Dr. Smith said hello. Then left.")
        assert any("Dr." in s for s in result)

    def test_empty_string(self):
        assert _split_sentences("") == []
