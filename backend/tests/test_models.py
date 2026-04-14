"""Tests for Musawo AI Pydantic models — request/response validation."""

import pytest
from pydantic import ValidationError
from app.models import ChatRequest, ChatResponse, Mode, Locale, Severity, TriageResult, RedFlag, EscalationAction


class TestChatRequest:
    """Validate ChatRequest constraints."""

    def test_valid_request(self):
        req = ChatRequest(query="child has fever", mode=Mode.VHT, locale=Locale.EN)
        assert req.query == "child has fever"
        assert req.mode == Mode.VHT

    def test_rejects_empty_query(self):
        with pytest.raises(ValidationError):
            ChatRequest(query="", mode=Mode.VHT)

    def test_rejects_overly_long_query(self):
        with pytest.raises(ValidationError):
            ChatRequest(query="x" * 2001, mode=Mode.VHT)

    def test_defaults_to_community_mode(self):
        req = ChatRequest(query="headache")
        assert req.mode == Mode.COMMUNITY

    def test_defaults_to_english_locale(self):
        req = ChatRequest(query="headache")
        assert req.locale == Locale.EN

    def test_accepts_pregnancy_week(self):
        req = ChatRequest(query="bleeding", mode=Mode.MATERNAL, pregnancy_week=28)
        assert req.pregnancy_week == 28

    def test_rejects_invalid_pregnancy_week(self):
        with pytest.raises(ValidationError):
            ChatRequest(query="bleeding", pregnancy_week=50)


class TestChatResponse:
    """Validate ChatResponse structure."""

    def test_includes_mandatory_disclaimer(self):
        resp = ChatResponse(
            answer="Take ORS",
            mode=Mode.VHT,
            locale=Locale.EN,
            confidence=0.8,
        )
        assert "not a medical diagnosis" in resp.disclaimer.lower()

    def test_confidence_range(self):
        with pytest.raises(ValidationError):
            ChatResponse(answer="x", mode=Mode.VHT, locale=Locale.EN, confidence=1.5)


class TestTriageResult:
    """Validate triage result structure."""

    def test_red_severity_with_flags(self):
        triage = TriageResult(
            severity=Severity.RED,
            red_flags=[
                RedFlag(
                    symptom="convulsions",
                    severity=Severity.RED,
                    action=EscalationAction.EMERGENCY_REFER,
                    detail="Danger sign",
                )
            ],
            refer_reasons=["convulsions"],
        )
        assert triage.severity == Severity.RED
        assert len(triage.red_flags) == 1

    def test_green_severity_manage_at_home(self):
        triage = TriageResult(
            severity=Severity.GREEN,
            manage_at_home=["Give ORS + Zinc for 10 days"],
        )
        assert len(triage.manage_at_home) == 1
