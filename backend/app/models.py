"""Pydantic schemas for Musawo AI — Community Health Navigator."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Mode(str, Enum):
    VHT = "vht"            # Village Health Team triage
    MATERNAL = "maternal"  # Maternal & newborn companion
    COMMUNITY = "community"  # General community health


class Locale(str, Enum):
    EN = "en"
    LG = "lg"    # Luganda
    NY = "nyn"   # Runyankole
    SW = "sw"    # Swahili


class Severity(str, Enum):
    GREEN = "green"    # Manage at home
    YELLOW = "yellow"  # Monitor, follow up in 24-48h
    RED = "red"        # Refer immediately


class EscalationAction(str, Enum):
    MANAGE_HOME = "manage_at_home"
    MONITOR = "monitor"
    REFER_HEALTH_CENTRE = "refer_health_centre"
    CALL_HOTLINE = "call_hotline"
    EMERGENCY_REFER = "emergency_refer"


# ---------------------------------------------------------------------------
# Request / Response
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    mode: Mode = Mode.COMMUNITY
    locale: Locale = Locale.EN
    session_id: Optional[str] = None
    # Maternal-specific
    pregnancy_week: Optional[int] = Field(None, ge=1, le=45)
    # Offline sync
    offline_id: Optional[str] = None


class Citation(BaseModel):
    ref: str
    source: str
    page: Optional[str] = None
    section: Optional[str] = None
    passage: Optional[str] = None


class RedFlag(BaseModel):
    symptom: str
    severity: Severity
    action: EscalationAction
    detail: str


class TriageResult(BaseModel):
    severity: Severity
    red_flags: list[RedFlag] = []
    manage_at_home: list[str] = []
    refer_reasons: list[str] = []
    follow_up: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    mode: Mode
    locale: Locale
    confidence: float = Field(..., ge=0.0, le=1.0)
    citations: list[Citation] = []
    faithfulness_score: Optional[float] = None
    triage: Optional[TriageResult] = None
    escalation_required: bool = False
    escalation_message: Optional[str] = None
    disclaimer: str = (
        "This is guidance only — not a medical diagnosis. "
        "If symptoms worsen, visit the nearest health facility immediately."
    )
    session_id: Optional[str] = None


class HealthStatus(BaseModel):
    status: str
    mode: str
    retriever_ready: bool
    llm_ready: bool
    version: str = "1.0.0"


# ---------------------------------------------------------------------------
# Maternal tracking
# ---------------------------------------------------------------------------

class MaternalProfile(BaseModel):
    expected_due_date: Optional[date] = None
    pregnancy_week: Optional[int] = None
    gravida: Optional[int] = None  # Number of pregnancies
    parity: Optional[int] = None   # Number of deliveries
    risk_factors: list[str] = []


class MedicationReminder(BaseModel):
    name: str
    dosage: str
    frequency: str
    next_due: Optional[str] = None


# ---------------------------------------------------------------------------
# Health facility
# ---------------------------------------------------------------------------

class HealthFacility(BaseModel):
    name: str
    level: str  # HC II, HC III, HC IV, Hospital
    district: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    phone: Optional[str] = None
    services: list[str] = []


class FeedbackRequest(BaseModel):
    session_id: str
    turn_id: str
    rating: int = Field(..., ge=-1, le=1)
    comment: Optional[str] = Field(None, max_length=500)
