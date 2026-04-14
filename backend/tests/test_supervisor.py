"""Tests for Musawo AI mode supervisor and red-flag detection."""

import pytest
from app.agents.supervisor import classify
from app.models import Mode, Severity


class TestModeClassification:
    """classify() must route queries to correct health mode."""

    def test_vht_query_routes_to_vht(self):
        result = classify("Child has malaria and fast breathing")
        assert result.mode == Mode.VHT

    def test_maternal_query_routes_to_maternal(self):
        result = classify("I am 28 weeks pregnant and have swollen feet")
        assert result.mode == Mode.MATERNAL

    def test_breastfeeding_routes_to_maternal(self):
        result = classify("My baby isn't breastfeeding well")
        assert result.mode == Mode.MATERNAL

    def test_community_query_routes_to_community(self):
        result = classify("Where is the nearest health centre?")
        assert result.mode == Mode.COMMUNITY

    def test_medication_routes_to_community(self):
        result = classify("What is the dosage of paracetamol?")
        assert result.mode == Mode.COMMUNITY

    def test_ambiguous_defaults_to_community(self):
        result = classify("I feel unwell today")
        assert result.mode == Mode.COMMUNITY

    def test_respects_current_mode_bias(self):
        result = classify("the child has fever", current_mode=Mode.VHT)
        assert result.mode == Mode.VHT

    def test_luganda_vht_query(self):
        result = classify("Omwana alina omusujja ne senyiga")
        # "omusujja" (fever) and "senyiga" (pneumonia) are VHT keywords
        assert result.mode == Mode.VHT

    def test_empty_query_low_confidence(self):
        result = classify("")
        assert result.confidence <= 0.3


class TestRedFlagDetection:
    """classify() must detect danger signs via regex patterns."""

    def test_detects_convulsions(self):
        result = classify("The child is having convulsions and fits")
        assert len(result.detected_symptoms) > 0
        assert result.severity_hint == Severity.RED

    def test_detects_unconscious(self):
        result = classify("The patient is unconscious and not responsive")
        assert "Unconscious / unresponsive" in result.detected_symptoms
        assert result.severity_hint == Severity.RED

    def test_detects_severe_bleeding(self):
        result = classify("She has severe bleeding after delivery")
        assert result.severity_hint == Severity.RED

    def test_detects_chest_indrawing(self):
        result = classify("The baby has chest indrawing when breathing")
        assert result.severity_hint == Severity.RED

    def test_detects_unable_to_drink(self):
        result = classify("The child is not able to drink anything")
        assert result.severity_hint == Severity.RED

    def test_detects_cord_infection(self):
        result = classify("The cord is red and swollen with pus")
        assert result.severity_hint == Severity.RED

    def test_no_false_positive_on_normal_query(self):
        result = classify("My child has a mild cough for 2 days")
        assert result.severity_hint is None
        assert len(result.detected_symptoms) == 0

    def test_multiple_danger_signs(self):
        result = classify("Baby has convulsions and is not able to breastfeed and has stiff neck")
        assert len(result.detected_symptoms) >= 2
        assert result.severity_hint == Severity.RED
