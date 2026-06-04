# Voice & Speech System v2.6 — Musawo AI

Streaming voice pipeline for multilingual health consultations in Luganda, Runyankole, Swahili, and English. Upgraded with hybrid VAD, on-device STT, prosody-aware TTS, and semantic endpointing.

## Architecture

```
Client speaks → PCM16 chunks → WebSocket
                                    ↓
                      ┌─── Energy Gate (fast, <0.1ms) ───┐
                      │         ↓ (energy detected)       │
                      │   Silero VAD ONNX (<1ms)          │
                      │   (neural speech confirmation)    │
                      │         ↓ (confirmed speech)      │
                      └──→ Utterance buffer               │
                           + Noise Gate                   │
                           + Semantic Endpointing         │
                                    ↓
                      ASR: [English] Cloudflare Whisper → OpenAI Whisper
                           [Ugandan] Sunbird → on-device → Browser
                                    ↓
                    [If Luganda/etc] MT → English (Sunbird)
                                    ↓
                          LLM (Gemini Flash via CF AI Gateway → Groq)
                          + RAG from MoH guidelines
                                    ↓
                    [If Luganda/etc] MT → local language
                                    ↓
                    Prosody detection (urgency → rate/pitch)
                                    ↓
                    Sentence-chunked TTS:
                    [English] Cloudflare MeloTTS / [Ugandan] Sunbird
                    (first audio in <250ms target)
                                    ↓
                    Client plays audio chunks
```

## v2.6 Upgrades

### Hybrid VAD (Silero + Energy)
- **Energy gate** as fast path — zero neural cost on silent frames
- **Silero VAD** (1.6MB ONNX) confirms speech when energy fires — eliminates noise false triggers
- Sensitivity presets tuned for village environments:
  - `low` (noisy clinic): energy=0.025, Silero threshold=0.6
  - `medium` (default): energy=0.015, Silero threshold=0.5
  - `high` (quiet room): energy=0.008, Silero threshold=0.35
- Env var `VOICE_SILERO_ENABLED` (default "true") to disable
- Requires `onnxruntime` (CPU-only, ~40MB)

### English voice via Cloudflare Workers AI (egress-safe)
English STT/TTS route through **Cloudflare Workers AI** over Cloudflare's reachable
edge — on the RENU pod `api.openai.com` (OpenAI Whisper) and `edge-tts`'s host are
firewalled, but Cloudflare is not (same reason Gemini uses the AI Gateway; see
[`egress-cloudflare-gateway.md`](egress-cloudflare-gateway.md)). Reuses the Cloudflare
account + a Workers AI token (`CF_API_TOKEN`).

| Direction | Model (`backend/app/sunbird.py`) | Output |
|-----------|----------------------------------|--------|
| STT | `@cf/openai/whisper-large-v3-turbo` (`CF_STT_MODEL`) | transcript (~1.5s) |
| TTS | `@cf/myshell-ai/melotts` (`CF_TTS_MODEL`) | base64 MP3 **data URL** the browser plays directly (~2.2s) |

Routing: **English** STT = Cloudflare Whisper → OpenAI Whisper → Sunbird/local;
**English** TTS = Cloudflare MeloTTS → local. **Ugandan** languages stay on Sunbird's
native STT/voices (far better for lg/nyn/sw), then local fallbacks.

### On-Device STT
- **@xenova/transformers** + `Xenova/whisper-tiny` (~50MB, cached in IndexedDB)
- Runs entirely in browser via Web Worker + ONNX Runtime WASM
- Automatic fallback when offline or all server STT fails
- STT mode badge in VoiceModal: "Sunbird" / "Offline" / "Browser"
- CSP requires `'wasm-unsafe-eval'` in production `script-src`

### Noise Gate
- Hard-gates residual noise below threshold before sending to STT
- Complements browser-side `noiseSuppression: true`
- Applied in `get_utterance_audio()` before ASR

### Semantic Endpointing
- Detects natural turn completions without waiting full silence duration
- Triggers at 200ms silence (vs 400-800ms) when turn is clearly complete
- Detection: question marks, EN/LG/NYN/SW completion phrases, short statements
- `feed_audio()` accepts optional `partial_transcript` for real-time detection

### Prosody-Aware TTS
- `_detect_prosody()` analyzes text + triage severity
- Red severity / REFER NOW: rate=1.1, pitch=1.15 (urgent)
- Yellow: rate=1.0, pitch=1.05
- Normal: rate=0.95, pitch=1.0 (slower for comprehension)
- Yields `prosody_hint` VoiceEvent before TTS audio chunks

### Connection Resilience
- WebSocket heartbeat: ping every 15s, reconnect on 30s timeout
- Exponential backoff with full jitter on reconnection
- Connection state tracking: disconnected → connecting → connected → reconnecting

### Voice Metrics (Prometheus)
- `musawo_voice_asr_latency_seconds` — ASR processing latency
- `musawo_voice_tts_first_chunk_seconds` — Time to first TTS audio
- `musawo_voice_session_total` — Voice sessions started
- `musawo_voice_barge_in_total` — Barge-in interruptions
- `musawo_voice_utterance_duration_seconds` — Utterance durations

## Endpoints

| Endpoint | Type | Description |
|----------|------|-------------|
| `POST /v1/voice/stt` | HTTP | Batch speech-to-text via Sunbird |
| `POST /v1/voice/tts` | HTTP | Batch text-to-speech via Sunbird |
| `WS /v1/voice/chat/stream` | WebSocket | Full streaming voice chat pipeline |

## WebSocket Protocol

### Client → Server

```json
{"type": "session_start", "language": "lg", "vad_sensitivity": "medium", "tts_enabled": true}
```
Then send binary PCM16 LE mono audio chunks (16kHz, 20ms recommended).
```json
{"type": "ping"}           // Heartbeat (every 15s)
{"type": "barge_in"}       // Interrupt AI mid-response
{"type": "session_end"}    // End session
```

### Server → Client

```json
{"type": "session_ready", "session_id": "abc123"}
{"type": "pong", "timestamp": 1715529600.0}
{"type": "vad_state", "speaking": true}
{"type": "transcript_final", "text": "Omwana wange alwadde", "language": "lg", "latency_s": 0.45}
{"type": "prosody_hint", "rate": 1.1, "pitch": 1.15, "urgency": "high"}
{"type": "audio_start", "sample_rate": 24000}
// [binary: TTS audio PCM16 LE]
{"type": "audio_end"}
{"type": "reply_text", "text": "Based on MoH guidelines...", "chunk_index": 0}
{"type": "reply_meta", "sources": [...], "confidence": 0.97}
{"type": "latency_report", "asr_ms": 450, "mt_in_ms": 120, "llm_ms": 800, "tts_first_chunk_ms": 250, "total_ms": 1620}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICE_VAD_ENERGY_THRESHOLD` | 0.015 | RMS energy cutoff |
| `VOICE_VAD_SILENCE_MS` | 600 | Silence to end utterance (ms) |
| `VOICE_VAD_MIN_SPEECH_MS` | 250 | Minimum speech to accept (ms) |
| `VOICE_VAD_MAX_UTTERANCE_S` | 30 | Hard cutoff (seconds) |
| `VOICE_SILERO_ENABLED` | true | Enable Silero neural VAD |
| `CF_API_TOKEN` | — | secret — Cloudflare Workers AI token (English STT/TTS) |
| `CF_STT_MODEL` | `@cf/openai/whisper-large-v3-turbo` | CF Workers AI Whisper (English STT) |
| `CF_TTS_MODEL` | `@cf/myshell-ai/melotts` | CF Workers AI MeloTTS (English TTS) |
| `SUNBIRD_USERNAME` / `SUNBIRD_API_TOKEN` (+ `SUNBIRD_FALLBACK_*`) | — | secret — Sunbird auth for Ugandan-language voice |

## Files

| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/voice_stream.py` | ~510 | Hybrid VAD + noise gate + prosody + streaming pipeline |
| `backend/app/voice_ws.py` | ~140 | WebSocket handler + ping/pong |
| `backend/app/sunbird.py` | 657 | Sunbird AI STT/TTS/MT (with token refresh) |
| `backend/app/metrics.py` | ~255 | Prometheus metrics (incl. voice) |
| `backend/tests/test_voice_vad.py` | 186 | 27 voice tests |
| `frontend/src/services/voiceWebSocket.ts` | ~300 | WebSocket client + heartbeat |
| `frontend/src/lib/voiceOutput.ts` | 259 | Browser TTS + Sunbird TTS |
| `frontend/src/lib/onDeviceSTT.ts` | 145 | On-device Whisper STT |
| `frontend/src/workers/whisperWorker.ts` | 85 | Whisper Web Worker |
| `frontend/src/components/VoiceModal.tsx` | ~440 | Voice input UI + offline fallback |

## Testing

```bash
# Run voice VAD tests (27 tests)
cd backend && python3 -m pytest tests/test_voice_vad.py -v

# Test batch STT
curl -X POST https://musawo-ai.renu-01.cranecloud.io/v1/voice/stt \
  -F "audio=@sample.wav" -F "language=lg"

# Test batch TTS
curl -X POST https://musawo-ai.renu-01.cranecloud.io/v1/voice/tts \
  -H "Content-Type: application/json" -d '{"text": "Hello", "locale": "en"}'

# WebSocket streaming
wscat -c wss://musawo-ai.renu-01.cranecloud.io/v1/voice/chat/stream
```
