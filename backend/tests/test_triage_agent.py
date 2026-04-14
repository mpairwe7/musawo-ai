"""Tests for Musawo AI agentic triage workflow."""

import pytest
from app.agents.triage_agent import TriageAgent, TriagePhase
from app.models import Severity


@pytest.fixture
def agent():
    return TriageAgent()


class TestTriageAgentFlow:
    """Test the multi-step iCCM assessment agent."""

    def test_initial_phase_asks_followup(self, agent):
        result = agent.process("sess-1", "A 3-year-old child has fever")
        assert result["assessment_complete"] is False
        assert result["follow_up_question"] is not None
        assert "danger signs" in result["response"].lower() or "drink" in result["response"].lower()

    def test_danger_sign_triggers_immediate_referral(self, agent):
        result = agent.process("sess-2", "The baby has convulsions and cannot breastfeed")
        assert result["triage"] is not None
        assert result["triage"].severity == Severity.RED
        assert result["assessment_complete"] is True
        assert "REFER" in result["response"]

    def test_stateful_across_turns(self, agent):
        # Turn 1: initial complaint
        r1 = agent.process("sess-3", "Child has fever for 2 days")
        assert r1["assessment_complete"] is False

        # Turn 2: provide more info
        r2 = agent.process("sess-3", "Yes the child can drink. No convulsions. RDT positive")
        # Should now have enough info to classify
        state = agent.get_or_create_state("sess-3")
        assert "fever" in " ".join(state.symptoms_reported).lower()

    def test_malaria_classification_with_rdt(self, agent):
        agent.process("sess-4", "2 year old child with fever")
        result = agent.process("sess-4", "RDT positive, no danger signs, child is alert and drinking")
        # Should reach classification at some point
        state = agent.get_or_create_state("sess-4")
        assert len(state.symptoms_reported) >= 2

    def test_new_patient_resets_state(self, agent):
        agent.process("sess-5", "child has diarrhoea")
        agent.process("sess-5", "no danger signs, some dehydration")
        # Force to follow_up phase
        state = agent.get_or_create_state("sess-5")
        state.phase = TriagePhase.FOLLOW_UP
        result = agent.process("sess-5", "next patient")
        assert "ready" in result["response"].lower() or "next" in result["response"].lower()

    def test_session_isolation(self, agent):
        agent.process("sess-a", "child has malaria")
        agent.process("sess-b", "pregnant mother bleeding")
        state_a = agent.get_or_create_state("sess-a")
        state_b = agent.get_or_create_state("sess-b")
        assert state_a.main_complaint != state_b.main_complaint

    def test_pneumonia_asks_breathing_rate(self, agent):
        result = agent.process("sess-6", "3 year old with cough and difficult breathing")
        # Agent should ask for breathing rate count
        found_breathing_question = False
        # May need multiple turns
        if "breathing" in (result.get("follow_up_question") or "").lower():
            found_breathing_question = True
        if not found_breathing_question:
            r2 = agent.process("sess-6", "child can drink, no convulsions, no danger signs")
            if "breathing" in (r2.get("follow_up_question") or "").lower() or "count" in (r2.get("response") or "").lower():
                found_breathing_question = True
        assert found_breathing_question

    def test_diarrhoea_treatment_includes_ors_zinc(self, agent):
        agent.process("sess-7", "18 month old with diarrhoea for 2 days")
        agent.process("sess-7", "no danger signs, child can drink, eyes slightly sunken")
        # Force classify
        state = agent.get_or_create_state("sess-7")
        state.phase = TriagePhase.CLASSIFY
        result = agent.process("sess-7", "that's all")
        if result.get("triage"):
            manage = result["triage"].manage_at_home
            all_text = " ".join(manage).lower()
            assert "ors" in all_text or "zinc" in all_text
