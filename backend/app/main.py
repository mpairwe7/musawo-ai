"""Musawo AI — FastAPI application entry point.

Health-hardened API with rate limiting, security headers, SSE streaming,
and graceful degradation.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from app.models import (
    ChatRequest,
    ChatResponse,
    FeedbackRequest,
    HealthFacility,
    HealthStatus,
    Mode,
)
from app.service import HealthService

logger = logging.getLogger("musawo")
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper()),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

# ── Config ─────────────────────────────────────────────────────────────────

APP_ENV = os.getenv("APP_ENV", "development")
PORT = int(os.getenv("PORT", "8000"))
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3200,http://localhost:8000,http://localhost:8888"
).split(",")
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "30"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

# ── Rate limiter (thread-safe, in-process) ─────────────────────────────────

from threading import Lock

_rate_store: dict[str, list[float]] = {}
_rate_lock = Lock()


def _check_rate_limit(ip: str, limit: int = RATE_LIMIT_REQUESTS, window: int = RATE_LIMIT_WINDOW) -> bool:
    now = time.time()
    with _rate_lock:
        if len(_rate_store) > 10_000:
            # Evict stale IPs
            cutoff = now - window * 2
            _rate_store.clear()

        if ip not in _rate_store:
            _rate_store[ip] = []

        _rate_store[ip] = [t for t in _rate_store[ip] if t > now - window]
        if len(_rate_store[ip]) >= limit:
            return False
        _rate_store[ip].append(now)
        return True


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


# ── Lifespan ───────────────────────────────────────────────────────────────

_service: HealthService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _service
    logger.info("Musawo AI starting up (env=%s)", APP_ENV)

    _service = HealthService()
    _service.initialize()

    logger.info("Musawo AI ready to serve")
    yield
    logger.info("Musawo AI shutting down")


# ── App ────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Musawo AI — Community Health Navigator",
    description="Offline-first health guidance for rural Uganda",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
)


# ── Security headers middleware ────────────────────────────────────────────

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "microphone=(self), geolocation=(self)"
    if APP_ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


# ── Rate limit middleware ──────────────────────────────────────────────────

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path in ("/health", "/ready"):
        return await call_next(request)

    ip = _get_client_ip(request)
    if not _check_rate_limit(ip):
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please try again later."},
        )
    return await call_next(request)


# ── Health endpoints ───────────────────────────────────────────────────────

@app.get("/health", response_model=HealthStatus)
async def health():
    return HealthStatus(
        status="ok" if _service and _service.is_ready else "degraded",
        mode="online" if _service and _service.retriever.is_ready else "offline",
        retriever_ready=bool(_service and _service.retriever.is_ready),
        llm_ready=bool(_service),
    )


@app.get("/ready")
async def readiness():
    if not _service or not _service.is_ready:
        raise HTTPException(503, "Service not ready")
    return {"status": "ready"}


# ── Prometheus metrics ─────────────────────────────────────────────────────

@app.get("/metrics")
async def prometheus_metrics():
    from app.metrics import get_metrics_text
    text, content_type = get_metrics_text()
    return Response(content=text, media_type=content_type)


# ── Chat endpoints ─────────────────────────────────────────────────────────

@app.post("/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    if not _service:
        raise HTTPException(503, "Service initializing")

    # Validate request ID if provided
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    if not re.match(r"^[a-zA-Z0-9\-]{1,128}$", request_id):
        raise HTTPException(400, "Invalid request ID format")

    import asyncio
    response = await asyncio.to_thread(_service.generate, req)
    return response


@app.post("/v1/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    if not _service:
        raise HTTPException(503, "Service initializing")

    import asyncio

    async def event_generator():
        # Run sync generator in thread pool to avoid blocking event loop
        gen = _service.stream_response(req)
        loop = asyncio.get_event_loop()
        while True:
            try:
                event = await loop.run_in_executor(None, next, gen)
            except StopIteration:
                break
            except Exception as e:
                logger.error("Stream error: %s", e)
                yield {"event": "error", "data": str(e)}
                break
            evt = event.get("event", "data")
            data = event.get("data", "")
            if isinstance(data, dict):
                data = json.dumps(data)
            yield {"event": evt, "data": data}

    return EventSourceResponse(event_generator())


# ── Agentic triage endpoint ─────────────────────────────────────────────────

@app.post("/v1/triage")
async def agentic_triage(req: ChatRequest, request: Request):
    """Multi-step agentic iCCM triage assessment.

    Unlike /v1/chat (single-shot RAG), this endpoint maintains
    a stateful assessment session that guides VHTs through:
    Assess → Classify → Treat/Refer following iCCM protocol.
    """
    if not _service:
        raise HTTPException(503, "Service initializing")

    import asyncio

    # Input guard
    from app.guardrails import InputGuard
    guard = InputGuard.check(req.query)
    if not guard.allowed:
        return {"response": guard.reason, "phase": "blocked", "triage": None,
                "follow_up_question": None, "assessment_complete": False}

    session_id = req.session_id or str(uuid.uuid4())

    result = await asyncio.to_thread(
        _service.triage_agent.process, session_id, req.query
    )

    # Serialize triage if present
    triage_data = None
    if result.get("triage"):
        triage_data = result["triage"].model_dump()

    return {
        "response": result["response"],
        "phase": result["phase"],
        "triage": triage_data,
        "follow_up_question": result.get("follow_up_question"),
        "assessment_complete": result.get("assessment_complete", False),
        "session_id": session_id,
    }


# ── Mode info ──────────────────────────────────────────────────────────────

@app.get("/v1/modes")
async def list_modes():
    return [
        {
            "id": "vht",
            "name": "VHT Triage",
            "name_lg": "Okulambula VHT",
            "icon": "stethoscope",
            "description": "For Village Health Team workers — symptom triage & iCCM protocols",
            "color": "#E74C3C",
        },
        {
            "id": "maternal",
            "name": "Maternal Care",
            "name_lg": "Obujjanjabi bw'Abakyala",
            "icon": "baby",
            "description": "Pregnancy, delivery & newborn care guidance",
            "color": "#E91E63",
        },
        {
            "id": "community",
            "name": "Community Health",
            "name_lg": "Obulamu bw'Ekitundu",
            "icon": "heart",
            "description": "General health guidance, medication reminders & clinic finder",
            "color": "#2E7D32",
        },
    ]


# ── Health facilities (loaded from KB registry) ─────────────────────────────

_FACILITIES: list[HealthFacility] = []


def _load_facilities() -> None:
    """Load facilities from knowledge-base JSON registry."""
    global _FACILITIES
    import json as _json
    from pathlib import Path

    # Try multiple paths (works in Docker /app and local dev)
    candidates = [
        Path("knowledge-base/health-facilities/uganda-facility-registry.json"),
        Path("../knowledge-base/health-facilities/uganda-facility-registry.json"),
        Path(__file__).parent.parent.parent / "knowledge-base/health-facilities/uganda-facility-registry.json",
    ]
    registry_path = None
    for p in candidates:
        if p.exists():
            registry_path = p
            break
    if registry_path is None:
        logger.warning("Facility registry not found in any expected location")
        return

    try:
        data = _json.loads(registry_path.read_text())
        for f in data.get("facilities", []):
            _FACILITIES.append(HealthFacility(
                name=f["name"],
                level=f["level"],
                district=f["district"],
                latitude=f.get("latitude"),
                longitude=f.get("longitude"),
                phone=f.get("phone"),
                services=f.get("services", []),
            ))
        logger.info("Loaded %d health facilities from registry", len(_FACILITIES))
    except Exception as e:
        logger.error("Failed to load facility registry: %s", e)


# Load on import
_load_facilities()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two GPS points in km."""
    import math
    R = 6371
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = (math.sin(dLat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dLon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@app.get("/v1/facilities")
async def list_facilities(
    district: str | None = None,
    level: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float = 50.0,
    limit: int = 20,
):
    """List health facilities, optionally filtered by district/level/proximity.

    If lat/lon provided, returns facilities sorted by distance (nearest first)
    within radius_km. Each facility includes a `distance_km` field.
    """
    facilities = _FACILITIES

    if district:
        facilities = [f for f in facilities if f.district.lower() == district.lower()]
    if level:
        facilities = [f for f in facilities if level.lower() in f.level.lower()]

    # GPS proximity sorting
    if lat is not None and lon is not None:
        results = []
        for f in facilities:
            if f.latitude is not None and f.longitude is not None:
                dist = _haversine_km(lat, lon, f.latitude, f.longitude)
                if dist <= radius_km:
                    results.append({
                        **f.model_dump(),
                        "distance_km": round(dist, 2),
                    })
        results.sort(key=lambda x: x["distance_km"])
        return results[:limit]

    return facilities[:limit]


@app.get("/v1/facilities/nearby")
async def nearby_facilities(
    lat: float,
    lon: float,
    radius_km: float = 30.0,
    limit: int = 5,
):
    """Find nearest health facilities to a GPS coordinate."""
    results = []
    for f in _FACILITIES:
        if f.latitude is not None and f.longitude is not None:
            dist = _haversine_km(lat, lon, f.latitude, f.longitude)
            if dist <= radius_km:
                results.append({
                    **f.model_dump(),
                    "distance_km": round(dist, 2),
                })
    results.sort(key=lambda x: x["distance_km"])
    return results[:limit]


# ── SMS/USSD Gateway (Twilio + USSD menu) ─────────────────────────────────

@app.post("/v1/ussd/callback")
async def ussd_callback(request: Request):
    """USSD callback webhook for feature phone menu navigation.

    Accepts application/x-www-form-urlencoded (standard for USSD gateways).
    """
    from app.sms_gateway import handle_ussd_callback
    form = await request.form()
    session_id = str(form.get("sessionId", ""))
    phone = str(form.get("phoneNumber", ""))
    text = str(form.get("text", ""))
    service_code = str(form.get("serviceCode", ""))
    resp = handle_ussd_callback(session_id, phone, text, service_code)
    return Response(content=resp, media_type="text/plain")


@app.post("/v1/sms/send")
async def send_sms_endpoint(phone: str, message: str):
    """Send SMS via Twilio to a phone number."""
    from app.sms_gateway import send_sms
    result = await send_sms(phone, message)
    if result["status"] == "sent":
        return result
    raise HTTPException(500, detail=result.get("error", "SMS send failed"))


@app.post("/v1/sms/webhook")
async def twilio_sms_webhook(request: Request):
    """Twilio incoming SMS webhook.

    Configure in Twilio console:
    Messaging > Phone Number > When a message comes in > Webhook URL:
    https://your-domain.com/v1/sms/webhook (HTTP POST)
    """
    from app.sms_gateway import handle_incoming_sms, send_sms

    form = await request.form()
    from_number = str(form.get("From", ""))
    body = str(form.get("Body", ""))

    if not from_number or not body:
        raise HTTPException(400, "Missing From or Body")

    # Generate response
    reply = await handle_incoming_sms(from_number, body)

    # Send reply via Twilio
    await send_sms(from_number, reply)

    # Return TwiML empty response (Twilio expects XML)
    twiml = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    return Response(content=twiml, media_type="application/xml")


# ── Session Resume ─────────────────────────────────────────────────────────

@app.get("/v1/session/{session_id}/history")
async def get_session_history(session_id: str):
    """Retrieve conversation history for a session.

    Allows resuming previous conversations after page refresh.
    """
    if not _service:
        raise HTTPException(503, "Service initializing")

    history = _service.sessions.get_history(session_id, window=20)
    if not history:
        return {"session_id": session_id, "turns": [], "found": False}

    return {
        "session_id": session_id,
        "turns": history,
        "found": True,
    }


# ── Feedback ───────────────────────────────────────────────────────────────

@app.post("/v1/feedback")
async def submit_feedback(req: FeedbackRequest):
    from app.metrics import record_feedback
    record_feedback(req.rating)
    logger.info(
        "Feedback: session=%s turn=%s rating=%d comment=%s",
        req.session_id, req.turn_id, req.rating, req.comment,
    )
    return {"status": "recorded", "message": "Thank you for your feedback."}


# ── Emergency contacts ─────────────────────────────────────────────────────

@app.get("/v1/emergency-contacts")
async def emergency_contacts():
    return {
        "health_hotline": {"number": "0800 100 263", "label": "MoH Health Hotline (toll-free)"},
        "ambulance": {"number": "0800 911 911", "label": "National Ambulance"},
        "maternal": {"number": "0800 100 263", "label": "Maternal Health Hotline"},
        "mental_health": {"number": "0800 100 263", "label": "Mental Health Support"},
        "poison_centre": {"number": "+256-414-270-975", "label": "Uganda Poison Centre"},
    }
