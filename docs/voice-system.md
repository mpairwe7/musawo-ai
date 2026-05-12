# Voice & Speech System — Musawo AI

Streaming voice pipeline for multilingual health consultations in Luganda, Runyankole, Swahili, and English.

## Architecture

```
Client speaks → PCM16 chunks → WebSocket
                                    ↓
                          Energy-based VAD
                          (silence 600ms → utterance complete)
                                    ↓
                          ASR (Sunbird AI cloud)
                                    ↓
                    [If Luganda/etc] MT → English (Sunbird)
                                    ↓
                          LLM (Groq llama-3.3-70b)
                          + RAG from MoH guidelines
                                    ↓
                    [If Luganda/etc] MT → local language
                                    ↓
                    Sentence-chunked TTS (Sunbird)
                    (first audio in <1s)
                                    ↓
                    Client plays audio chunks
```

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
{"type": "barge_in"}     // Interrupt AI mid-response
{"type": "session_end"}  // End session
```

### Server → Client

```json
{"type": "session_ready", "session_id": "abc123"}
{"type": "vad_state", "speaking": true}
{"type": "transcript_final", "text": "Omwana wange alwadde", "language": "lg", "latency_s": 0.45}
{"type": "audio_start", "sample_rate": 24000}
// [binary: TTS audio PCM16 LE]
{"type": "audio_end"}
{"type": "reply_text", "text": "Based on MoH guidelines...", "chunk_index": 0}
{"type": "reply_meta", "sources": [...], "confidence": 0.97}
{"type": "latency_report", "asr_ms": 450, "mt_in_ms": 120, "llm_ms": 800, "tts_first_chunk_ms": 250, "total_ms": 1620}
```

## Voice Activity Detection (VAD)

Energy-based VAD with configurable thresholds (no neural model needed):

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| Energy threshold | `VOICE_VAD_ENERGY_THRESHOLD` | 0.015 | RMS energy cutoff |
| Silence duration | `VOICE_VAD_SILENCE_MS` | 600ms | Silence to end utterance |
| Min speech | `VOICE_VAD_MIN_SPEECH_MS` | 250ms | Minimum speech to accept |
| Max utterance | `VOICE_VAD_MAX_UTTERANCE_S` | 30s | Hard cutoff |

Sensitivity presets: `low` (noisy environments), `medium` (default), `high` (quiet rooms).

## Features

- **Sentence-chunked TTS**: LLM output split into sentences, each TTS'd independently for sub-second time-to-first-audio
- **Barge-in**: User can interrupt AI mid-response by speaking
- **Multilingual**: Detect language → translate → LLM → translate back (Luganda, Runyankole, Swahili)
- **Latency reporting**: Per-turn breakdown of ASR/MT/LLM/TTS timing
- **Rate limiting**: 100 audio frames/sec, 64KB max per frame

## Sunbird AI Integration

Cloud STT/TTS/MT for Ugandan languages:

| Service | API | Languages |
|---------|-----|-----------|
| STT | `POST /tasks/modal/stt` | English, Luganda, Runyankole, Acholi, Swahili |
| TTS | `POST /tasks/modal/tts` | Luganda (female 248), Runyankole (female 243), Swahili (male 246) |
| MT | `POST /tasks/modal/translate` | eng↔lug, eng↔nyn, eng↔ach, eng↔swa |
| Detect | `POST /tasks/modal/language_detect` | All supported |

Token refresh: auto-refresh every 6 days (7-day expiry). Credentials: `SUNBIRD_API_TOKEN` or `SUNBIRD_USERNAME`/`SUNBIRD_PASSWORD`.

## LLM Fallback Chain

```
Groq (free, fast) → Claude API → Local Qwen3 (GGUF/BnB) → Passage-based
```

For voice, Groq is recommended (500 tok/s, free tier). Local Qwen3 adds ~2s latency per turn.

## Files

| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/voice_stream.py` | 301 | VAD + streaming pipeline engine |
| `backend/app/voice_ws.py` | 136 | WebSocket handler |
| `backend/app/sunbird.py` | 657 | Sunbird AI STT/TTS/MT (with token refresh) |
| `frontend/src/services/voiceWebSocket.ts` | 186 | WebSocket client + AudioRecorder |
| `frontend/src/lib/voiceOutput.ts` | 259 | Browser TTS + Sunbird TTS |

## Deployment

WebSocket requires nginx `Upgrade` header support (configured in `Dockerfile.cranecloud`):

```nginx
location /v1/voice/ {
    proxy_pass http://127.0.0.1:8081/v1/voice/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 300s;
}
```

## Testing

```bash
# Test batch STT
curl -X POST https://musawo-ai-c29604f0.renu-01.cranecloud.io/v1/voice/stt \
  -H "Content-Type: audio/wav" --data-binary @sample.wav

# Test batch TTS
curl -X POST https://musawo-ai-c29604f0.renu-01.cranecloud.io/v1/voice/tts \
  -H "Content-Type: application/json" -d '{"text": "Hello", "language": "en"}'

# WebSocket: use browser console or wscat
wscat -c wss://musawo-ai-c29604f0.renu-01.cranecloud.io/v1/voice/chat/stream
```
