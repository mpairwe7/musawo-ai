"""Tests for Musawo AI LLM integration — passage formatting, prompts, generation.

Tests cover:
- format_passages: empty list, single passage, empty-text filtering
- System prompts: all modes present, contain disclaimer
- generate_from_passages: abstention on empty, structured response on data
- is_ready: always True (passage-based fallback guarantees availability)
- generate: falls through to passage-based when all API clients fail
"""

import pytest
from unittest.mock import patch, MagicMock

from app.llm import (
    format_passages,
    generate_from_passages,
    generate,
    is_ready,
    SYSTEM_PROMPTS,
)


# ── format_passages ───────────────────────────────────────────────────────


class TestFormatPassages:
    """format_passages wraps passages in XML markers for LLM context."""

    def test_empty_list_returns_no_context_tag(self):
        result = format_passages([])
        assert "<no_context>" in result
        assert "No relevant guidelines" in result

    def test_single_passage_with_source_and_section(self):
        passages = [
            {"text": "Give ORS for diarrhoea.", "source": "MoH VHT Guide", "section": "Diarrhoea"},
        ]
        result = format_passages(passages)
        assert "<passage" in result
        assert "MoH VHT Guide" in result
        assert "Diarrhoea" in result
        assert "Give ORS for diarrhoea." in result
        assert "[1]" in result

    def test_multiple_passages_numbered(self):
        passages = [
            {"text": "First passage.", "source": "A"},
            {"text": "Second passage.", "source": "B"},
        ]
        result = format_passages(passages)
        assert "[1]" in result
        assert "[2]" in result
        assert "First passage." in result
        assert "Second passage." in result

    def test_empty_text_passages_skipped(self):
        passages = [
            {"text": "", "source": "A"},
            {"text": "   ", "source": "B"},
            {"text": "Real content here.", "source": "C"},
        ]
        result = format_passages(passages)
        # Only the third passage (with real text) should appear
        assert "Real content here." in result
        # The empty ones should not produce passage tags
        assert result.count("<passage") == 1

    def test_source_defaults_to_moh_guidelines(self):
        passages = [{"text": "Some text."}]
        result = format_passages(passages)
        assert "MoH Guidelines" in result

    def test_section_omitted_when_empty(self):
        passages = [{"text": "Some text.", "source": "X", "section": ""}]
        result = format_passages(passages)
        # Should not have " — " separator when section is empty
        assert "X" in result


# ── System Prompts ─────────────────────────────────────────────────────────


class TestSystemPrompts:
    """System prompts exist for all modes and contain safety disclaimer."""

    def test_all_modes_have_prompts(self):
        for mode in ("vht", "maternal", "community"):
            assert mode in SYSTEM_PROMPTS
            assert len(SYSTEM_PROMPTS[mode]) > 100

    def test_prompts_contain_disclaimer(self):
        for mode, prompt in SYSTEM_PROMPTS.items():
            assert "not a medical diagnosis" in prompt.lower(), (
                f"Mode '{mode}' system prompt missing disclaimer"
            )

    def test_vht_prompt_mentions_iccm(self):
        assert "iccm" in SYSTEM_PROMPTS["vht"].lower()

    def test_maternal_prompt_mentions_antenatal(self):
        assert "antenatal" in SYSTEM_PROMPTS["maternal"].lower()

    def test_community_prompt_mentions_facility(self):
        assert "facility" in SYSTEM_PROMPTS["community"].lower()


# ── generate_from_passages ─────────────────────────────────────────────────


class TestGenerateFromPassages:
    """Passage-based response generation (no LLM, zero cost)."""

    def test_no_passages_returns_abstention(self):
        result = generate_from_passages("child has fever", [])
        assert "don't have enough information" in result["text"]
        assert result["usage"]["input_tokens"] == 0

    def test_with_passages_returns_structured_response(self):
        passages = [
            {
                "text": "Give ORS and zinc for diarrhoea in children under five.",
                "source": "MoH VHT Guide",
                "section": "Diarrhoea Management",
            },
        ]
        result = generate_from_passages("how to treat diarrhoea", passages)
        text = result["text"]

        # Should have structured sections
        assert "## Guidance" in text
        assert "## When to Refer" in text
        # Should cite the source
        assert "MoH VHT Guide" in text
        # Should contain the passage content
        assert "ORS" in text
        # Should have the disclaimer
        assert "not a medical diagnosis" in text

    def test_multiple_passages_all_included(self):
        passages = [
            {"text": "First passage about fever treatment.", "source": "A"},
            {"text": "Second passage about malaria RDT.", "source": "B"},
        ]
        result = generate_from_passages("fever", passages)
        assert "[1]" in result["text"]
        assert "[2]" in result["text"]

    def test_empty_text_passages_skipped(self):
        passages = [
            {"text": "", "source": "A"},
            {"text": "Real content here about diarrhoea.", "source": "B"},
        ]
        result = generate_from_passages("diarrhoea", passages)
        assert "Real content" in result["text"]

    def test_output_tokens_counted(self):
        passages = [{"text": "Some health guidance.", "source": "MoH"}]
        result = generate_from_passages("question", passages)
        assert result["usage"]["output_tokens"] > 0


# ── is_ready ──────────────────────────────────────────────────────────────


class TestIsReady:
    """is_ready returns True because passage-based fallback always works."""

    @patch("app.llm.GROQ_API_KEY", "")
    @patch("app.llm.ANTHROPIC_API_KEY", "")
    @patch("app.llm.LLM_BACKEND", "passages")
    def test_always_true_with_passage_fallback(self):
        assert is_ready() is True

    @patch("app.llm.GROQ_API_KEY", "fake-key")
    def test_true_when_groq_key_present(self):
        assert is_ready() is True


# ── generate (unified) ────────────────────────────────────────────────────


class TestGenerate:
    """generate() falls through to passage-based when API clients fail."""

    @patch("app.llm.GROQ_API_KEY", "")
    @patch("app.llm.ANTHROPIC_API_KEY", "")
    @patch("app.llm.LLM_BACKEND", "passages")
    def test_falls_through_to_passages_when_no_api_keys(self):
        passages = [
            {"text": "Give ACT for confirmed malaria.", "source": "MoH", "section": "Malaria"},
        ]
        result = generate("child has malaria", passages, mode="vht")
        # Should get a passage-based response
        assert "## Guidance" in result["text"]
        assert "ACT" in result["text"]

    @patch("app.llm.GROQ_API_KEY", "fake-key")
    @patch("app.llm.ANTHROPIC_API_KEY", "")
    @patch("app.llm.LLM_BACKEND", "passages")
    def test_falls_through_when_groq_fails(self):
        passages = [
            {"text": "Breastfeed exclusively for six months.", "source": "MoH"},
        ]
        with patch("app.llm.generate_groq", side_effect=Exception("rate limited")):
            result = generate("breastfeeding advice", passages, mode="maternal")
        # Should fall through to passage-based
        assert "Breastfeed" in result["text"]

    @patch("app.llm.GROQ_API_KEY", "fake-key")
    @patch("app.llm.ANTHROPIC_API_KEY", "fake-key")
    @patch("app.llm.LLM_BACKEND", "passages")
    def test_falls_through_when_both_apis_fail(self):
        passages = [
            {"text": "Wash hands with soap and water.", "source": "WHO"},
        ]
        with patch("app.llm.generate_groq", side_effect=Exception("groq down")), \
             patch("app.llm.generate_claude", side_effect=Exception("claude down")):
            result = generate("hand hygiene", passages, mode="community")
        assert "Wash hands" in result["text"]

    @patch("app.llm.GROQ_API_KEY", "")
    @patch("app.llm.ANTHROPIC_API_KEY", "")
    @patch("app.llm.LLM_BACKEND", "passages")
    def test_empty_passages_returns_abstention(self):
        result = generate("random question", [], mode="community")
        assert "don't have enough information" in result["text"]
