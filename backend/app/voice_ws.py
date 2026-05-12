"""WebSocket handler for streaming voice chat.

Protocol:
    Client → Server:
        {type: "session_start", language, vad_sensitivity, tts_enabled}
        [binary: PCM16 LE mono audio chunks, 20ms]
        {type: "barge_in"}
        {type: "session_end"}

    Server → Client:
        {type: "session_ready", session_id}
        {type: "vad_state", speaking: bool}
        {type: "transcript_final", text, language, latency_s}
        {type: "audio_start", sample_rate}
        [binary: TTS audio]
        {type: "audio_end"}
        {type: "reply_text", text, chunk_index}
        {type: "reply_meta", sources, confidence}
        {type: "latency_report", asr_ms, mt_in_ms, llm_ms, tts_first_chunk_ms, total_ms}
        {type: "error", detail, recoverable}
"""

from __future__ import annotations

import json
import logging
import time
import uuid

from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from .voice_stream import VADConfig, VoiceEvent, VoiceSession

logger = logging.getLogger(__name__)

# Rate limiting
_MAX_FRAMES_PER_SEC = 100
_MAX_FRAME_BYTES = 64 * 1024


async def voice_stream_ws(
    websocket: WebSocket,
    sunbird_module,
    generate_fn,
) -> None:
    """Handle one streaming voice WebSocket connection."""
    await websocket.accept()
    session: VoiceSession | None = None
    session_id = str(uuid.uuid4())[:12]
    frame_count = 0
    frame_reset = time.time()

    try:
        while True:
            raw = await websocket.receive()

            # Text message (JSON control frames)
            if "text" in raw:
                try:
                    msg = json.loads(raw["text"])
                except json.JSONDecodeError:
                    await _send(websocket, VoiceEvent("error", {"detail": "Invalid JSON", "recoverable": True}))
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "session_start":
                    language = msg.get("language", "en")
                    sensitivity = msg.get("vad_sensitivity", "medium")
                    tts_enabled = msg.get("tts_enabled", True)
                    vad = VADConfig.from_sensitivity(sensitivity)

                    session = VoiceSession(
                        session_id=session_id,
                        sunbird_module=sunbird_module,
                        generate_fn=generate_fn,
                        vad_config=vad,
                        language=language,
                        tts_enabled=tts_enabled,
                    )

                    await _send(websocket, VoiceEvent("session_ready", {"session_id": session_id}))
                    logger.info("Voice session %s started (lang=%s)", session_id, language)

                elif msg_type == "barge_in" and session:
                    session.barge_in()

                elif msg_type == "session_end":
                    logger.info("Voice session %s ended by client", session_id)
                    break

            # Binary message (audio data)
            elif "bytes" in raw and raw["bytes"] and session:
                pcm16 = raw["bytes"]

                # Rate limit
                now = time.time()
                if now - frame_reset >= 1.0:
                    frame_count = 0
                    frame_reset = now
                frame_count += 1
                if frame_count > _MAX_FRAMES_PER_SEC or len(pcm16) > _MAX_FRAME_BYTES:
                    continue

                # Feed to VAD
                event = session.feed_audio(pcm16)
                if event:
                    await _send(websocket, event)

                    # If utterance ready, process it
                    if event.data.get("utterance_ready"):
                        audio = session.get_utterance_audio()
                        async for reply_event in session.process_utterance(audio):
                            if reply_event.type == "audio_chunk":
                                # Send binary audio
                                audio_data = reply_event.data.get("audio")
                                if audio_data and isinstance(audio_data, bytes):
                                    await websocket.send_bytes(audio_data)
                            else:
                                await _send(websocket, reply_event)

    except WebSocketDisconnect:
        logger.info("Voice session %s disconnected", session_id)
    except Exception as e:
        logger.exception("Voice session %s error: %s", session_id, e)
        if websocket.client_state == WebSocketState.CONNECTED:
            await _send(websocket, VoiceEvent("error", {"detail": str(e), "recoverable": False}))
    finally:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()


async def _send(ws: WebSocket, event: VoiceEvent) -> None:
    """Send a VoiceEvent as JSON text."""
    if ws.client_state == WebSocketState.CONNECTED:
        await ws.send_json({"type": event.type, **event.data})
