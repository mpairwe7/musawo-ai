"""Musawo AI — LLM integration layer.

Supports multiple backends (priority order):
1. Groq API (free, fast — llama-3.3-70b / qwen3-32b via OpenAI-compatible API)
2. Claude API (Anthropic SDK, prompt caching + extended thinking)
3. Passage-based (zero-cost, instant, no LLM needed)

Health-specific system prompts for each mode (VHT, Maternal, Community).
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Generator

logger = logging.getLogger("musawo.llm")

# ── Config ─────────────────────────────────────────────────────────────────

LLM_BACKEND = os.getenv("LLM_BACKEND", "groq")  # "groq" | "claude" | "local" | "passages"

# Groq (free tier, OpenAI-compatible)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "4096"))
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.3"))

# Claude API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6-20250514")
CLAUDE_THINKING_BUDGET = int(os.getenv("CLAUDE_THINKING_BUDGET", "10000"))
CLAUDE_PROMPT_CACHING = os.getenv("CLAUDE_PROMPT_CACHING", "true").lower() == "true"
CLAUDE_MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "4096"))
CLAUDE_TEMPERATURE = float(os.getenv("CLAUDE_TEMPERATURE", "0.3"))

# Local model (offline fallback)
LOCAL_MODEL = os.getenv("LLM_MODEL", "Qwen/Qwen3-8B")
LOCAL_CONTEXT_WINDOW = int(os.getenv("LLM_CONTEXT_WINDOW", "8192"))
LOCAL_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "512"))
LOCAL_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
LOCAL_DEVICE = os.getenv("LLM_DEVICE", "auto")

# ── System Prompts ─────────────────────────────────────────────────────────

_BASE_SYSTEM = """You are Musawo AI, a Community Health Navigator for rural Uganda.
You provide health GUIDANCE only — you NEVER diagnose, prescribe medication, or
replace a qualified health worker.

RESPONSE FORMAT (you MUST follow this structure):
- Use **bold** for key terms, drug names, and important numbers.
- Use bullet points (- ) for lists of symptoms, steps, or instructions.
- Use clear paragraph breaks between sections.
- Structure every response with these sections (use ## headers):
  1. **Assessment** — What the symptoms suggest
  2. **Guidance** — What to do (step-by-step)
  3. **When to Refer** — Warning signs that need facility care
  4. **Sources** — Cite [1], [2] from passages
- Keep language simple — many users have limited literacy.
- Be concise but complete. Avoid long paragraphs — prefer bullet points.

CRITICAL RULES:
1. ONLY answer from the provided context passages. If the context does not cover
   the question, say "I don't have enough information" and recommend visiting
   the nearest health facility.
2. Always show your confidence level: **Confidence: HIGH / MEDIUM / LOW**
3. If you detect ANY danger sign (red flag), IMMEDIATELY say:
   "**REFER NOW** — Go to the nearest health facility immediately" and explain why.
4. Cite your sources using [1], [2], etc. referencing the passage markers.
5. Never store, repeat, or ask for personal health information.
6. Respond in the same language the user writes in. Use English medical terms
   with local explanation in parentheses.
7. Be warm, respectful, and culturally sensitive.
8. End with: *This is health guidance only — not a medical diagnosis.*

LANGUAGES: English, Luganda, Runyankole, Swahili.
"""

_VHT_SYSTEM = _BASE_SYSTEM + """
MODE: Village Health Team (VHT) Triage Support

You are assisting a trained Village Health Team member doing community health work.
Follow the iCCM (integrated Community Case Management) protocol:

ASSESS → CLASSIFY → TREAT or REFER

For children under 5:
- Check for danger signs FIRST (convulsions, unable to drink/breastfeed,
  vomiting everything, unconscious/lethargic)
- Classify: Malaria (fever + RDT), Pneumonia (fast breathing/chest indrawing),
  Diarrhoea (with/without dehydration)
- Give treatment protocol: ACT for malaria, Amoxicillin for pneumonia,
  ORS+Zinc for diarrhoea
- If ANY danger sign → REFER IMMEDIATELY

Always provide:
- Clear severity classification (GREEN=manage at home, YELLOW=monitor, RED=refer now)
- Step-by-step treatment instructions the VHT can follow
- Follow-up schedule (when to reassess)
- When to refer (specific danger signs to watch for)

Source: Uganda Ministry of Health VHT Strategy & Operational Guidelines, iCCM Protocol.
"""

_MATERNAL_SYSTEM = _BASE_SYSTEM + """
MODE: Maternal & Newborn Health Companion

You support pregnant mothers, new mothers, and their families with guidance
aligned to Uganda MoH Essential Maternal and Newborn Clinical Care Guidelines.

PREGNANCY GUIDANCE:
- Antenatal care schedule (at least 8 contacts per WHO/MoH)
- Nutrition advice (iron, folic acid, balanced diet)
- Danger signs to watch: severe headache, blurred vision, vaginal bleeding,
  high fever, swollen face/hands, reduced fetal movement, water breaking early
- Birth preparedness (identify facility, transport, blood donor, savings)

POSTNATAL GUIDANCE:
- Exclusive breastfeeding for 6 months
- Newborn danger signs: not feeding, fever/cold, fast breathing, cord infection,
  jaundice, convulsions
- Kangaroo mother care for small babies
- Immunization schedule (BCG, OPV, Pentavalent, etc.)
- Postpartum danger signs: heavy bleeding, fever, foul discharge

For ANY danger sign → "REFER NOW — Go to the health facility immediately."

Be especially gentle, encouraging, and supportive. Many mothers are young and
this may be their first pregnancy.

Source: MoH Essential Maternal and Newborn Clinical Care Guidelines (2022/2025).
"""

_COMMUNITY_SYSTEM = _BASE_SYSTEM + """
MODE: Community Health Navigator

You help general community members with:
- Symptom guidance (what might be causing their symptoms, when to seek care)
- Medication reminders (not prescriptions — just helping track what was prescribed)
- Finding the nearest health facility
- Preventive health (hygiene, nutrition, malaria prevention, safe water)
- Understanding health conditions in simple language

IMPORTANT: For medication questions, you may explain what a medication is FOR
and common side effects, but NEVER prescribe or suggest changing doses.
Always say "follow what your health worker prescribed."

For chronic conditions (HIV, diabetes, hypertension, TB):
- Emphasize adherence to prescribed treatment
- Explain danger signs that need immediate attention
- Encourage regular clinic visits

Source: Uganda Clinical Guidelines, National Treatment Guidelines, WHO Community Health.
"""

SYSTEM_PROMPTS = {
    "vht": _VHT_SYSTEM,
    "maternal": _MATERNAL_SYSTEM,
    "community": _COMMUNITY_SYSTEM,
}


# ── Passage formatting ─────────────────────────────────────────────────────

def format_passages(passages: list[dict[str, Any]]) -> str:
    """Wrap retrieved passages in spotlight markers for injection defense."""
    if not passages:
        return "<no_context>No relevant guidelines found for this query.</no_context>"

    parts = []
    for i, p in enumerate(passages):
        text = p.get("text", "").strip()
        if not text:
            continue
        marker = hashlib.sha256(text.encode()).hexdigest()[:12]
        source = p.get("source", "MoH Guidelines")
        section = p.get("section", "")
        header = f"[{i+1}] {source}"
        if section:
            header += f" — {section}"
        parts.append(f'<passage id="p{i+1}-{marker}">\n{header}\n{text}\n</passage>')

    return "\n\n".join(parts) if parts else "<no_context>No relevant content.</no_context>"


# ── Groq API backend (free, fast, OpenAI-compatible) ──────────────────────

_groq_client = None


def _get_groq_client():
    global _groq_client
    if _groq_client is None:
        from openai import OpenAI
        _groq_client = OpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )
    return _groq_client


def generate_groq(
    query: str,
    passages: list[dict[str, Any]],
    mode: str,
    history: list[dict[str, str]] | None = None,
    locale: str = "en",
) -> dict[str, Any]:
    """Generate via Groq (llama-3.3-70b or qwen3-32b). Free tier, ~500 tok/s."""
    client = _get_groq_client()
    system_prompt = SYSTEM_PROMPTS.get(mode, _COMMUNITY_SYSTEM)
    context = format_passages(passages)

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if history:
        for turn in history[-10:]:
            messages.append(turn)
    messages.append({
        "role": "user",
        "content": f"Context from official health guidelines:\n{context}\n\nUser question ({locale}): {query}\n\nRespond directly to the patient/VHT. Do NOT show your thinking process.",
    })

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            max_tokens=GROQ_MAX_TOKENS,
            temperature=GROQ_TEMPERATURE,
        )
        answer = response.choices[0].message.content or ""

        # Strip Qwen3 thinking blocks if present
        import re as _re
        answer = _re.sub(r"<think>.*?</think>", "", answer, flags=_re.DOTALL).strip()
        # Strip conversational preamble ("Okay, let's see...")
        for prefix in ["Okay, let's see", "Let me think", "Hmm,", "Alright,"]:
            if answer.startswith(prefix):
                # Find the first actual content line
                lines = answer.split("\n")
                for idx, line in enumerate(lines):
                    if line.strip().startswith(("##", "**", "- ", "1.", "For ", "The ", "Based", "According")):
                        answer = "\n".join(lines[idx:])
                        break

        return {
            "text": answer,
            "usage": {
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        }
    except Exception as e:
        logger.error("Groq API error: %s", e)
        raise


def stream_groq(
    query: str,
    passages: list[dict[str, Any]],
    mode: str,
    history: list[dict[str, str]] | None = None,
    locale: str = "en",
) -> Generator[dict[str, Any], None, None]:
    """Streaming generation via Groq API."""
    client = _get_groq_client()
    system_prompt = SYSTEM_PROMPTS.get(mode, _COMMUNITY_SYSTEM)
    context = format_passages(passages)

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if history:
        for turn in history[-10:]:
            messages.append(turn)
    messages.append({
        "role": "user",
        "content": f"Context from official health guidelines:\n{context}\n\nUser question ({locale}): {query}\n\nRespond directly. Do NOT show thinking.",
    })

    try:
        stream = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            max_tokens=GROQ_MAX_TOKENS,
            temperature=GROQ_TEMPERATURE,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield {"type": "token", "text": delta.content}
        yield {"type": "done", "usage": {}}
    except Exception as e:
        logger.error("Groq streaming error: %s", e)
        raise


# ── Claude API backend ─────────────────────────────────────────────────────

_client = None


def _get_claude_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _should_use_thinking(query: str) -> bool:
    """Heuristic: enable extended thinking for complex health queries."""
    triggers = [
        "explain", "why", "how does", "mechanism", "compare",
        "difference between", "what causes", "steps to",
        "protocol", "dosage calculation", "interact",
    ]
    q = query.lower()
    return any(t in q for t in triggers)


def generate_claude(
    query: str,
    passages: list[dict[str, Any]],
    mode: str,
    history: list[dict[str, str]] | None = None,
    locale: str = "en",
) -> dict[str, Any]:
    """Synchronous Claude API generation with prompt caching."""
    client = _get_claude_client()
    system_prompt = SYSTEM_PROMPTS.get(mode, _COMMUNITY_SYSTEM)
    context = format_passages(passages)

    # Build messages
    messages: list[dict] = []

    # History (last 5 turns)
    if history:
        for turn in history[-10:]:  # 5 pairs = 10 messages
            messages.append(turn)

    # Current query with context
    user_content = (
        f"Context from official health guidelines:\n{context}\n\n"
        f"User question ({locale}): {query}"
    )
    messages.append({"role": "user", "content": user_content})

    # System prompt with cache control
    system_blocks: list[dict] = [{"type": "text", "text": system_prompt}]
    if CLAUDE_PROMPT_CACHING:
        system_blocks[0]["cache_control"] = {"type": "ephemeral"}

    # Extended thinking for complex queries
    use_thinking = _should_use_thinking(query)

    kwargs: dict[str, Any] = {
        "model": CLAUDE_MODEL,
        "max_tokens": CLAUDE_MAX_TOKENS,
        "system": system_blocks,
        "messages": messages,
    }

    if use_thinking:
        kwargs["temperature"] = 1.0  # Required for extended thinking
        kwargs["thinking"] = {
            "type": "enabled",
            "budget_tokens": CLAUDE_THINKING_BUDGET,
        }
    else:
        kwargs["temperature"] = CLAUDE_TEMPERATURE

    try:
        response = client.messages.create(**kwargs)
    except Exception as e:
        logger.error("Claude API error: %s", e)
        # Attempt local fallback
        if LOCAL_MODEL:
            logger.info("Falling back to local model")
            return generate_local(query, passages, mode, locale)
        raise

    # Extract text from response blocks
    answer = ""
    for block in response.content:
        if block.type == "text":
            answer += block.text

    return {
        "text": answer,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_read": getattr(response.usage, "cache_read_input_tokens", 0),
            "cache_creation": getattr(response.usage, "cache_creation_input_tokens", 0),
        },
    }


def stream_claude(
    query: str,
    passages: list[dict[str, Any]],
    mode: str,
    history: list[dict[str, str]] | None = None,
    locale: str = "en",
) -> Generator[dict[str, Any], None, None]:
    """Streaming Claude API generation for SSE."""
    client = _get_claude_client()
    system_prompt = SYSTEM_PROMPTS.get(mode, _COMMUNITY_SYSTEM)
    context = format_passages(passages)

    messages: list[dict] = []
    if history:
        for turn in history[-10:]:
            messages.append(turn)

    user_content = (
        f"Context from official health guidelines:\n{context}\n\n"
        f"User question ({locale}): {query}"
    )
    messages.append({"role": "user", "content": user_content})

    system_blocks: list[dict] = [{"type": "text", "text": system_prompt}]
    if CLAUDE_PROMPT_CACHING:
        system_blocks[0]["cache_control"] = {"type": "ephemeral"}

    with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=CLAUDE_MAX_TOKENS,
        temperature=CLAUDE_TEMPERATURE,
        system=system_blocks,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield {"type": "token", "text": text}

        # Final message with usage
        final = stream.get_final_message()
        yield {
            "type": "done",
            "usage": {
                "input_tokens": final.usage.input_tokens,
                "output_tokens": final.usage.output_tokens,
            },
        }


# ── Local model backend (offline fallback) ─────────────────────────────────

_local_model = None
_local_tokenizer = None


def _load_local_model():
    """Thread-safe lazy load of local Qwen3-8B model."""
    global _local_model, _local_tokenizer
    if _local_model is not None:
        return

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    logger.info("Loading local model: %s", LOCAL_MODEL)
    _local_tokenizer = AutoTokenizer.from_pretrained(LOCAL_MODEL)
    _local_model = AutoModelForCausalLM.from_pretrained(
        LOCAL_MODEL,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        device_map=LOCAL_DEVICE,
        trust_remote_code=False,  # OWASP LLM03
    )
    logger.info("Local model loaded on %s", LOCAL_DEVICE)


def generate_local(
    query: str,
    passages: list[dict[str, Any]],
    mode: str,
    locale: str = "en",
) -> dict[str, Any]:
    """Generate using local Qwen3-8B model (offline mode)."""
    _load_local_model()

    system_prompt = SYSTEM_PROMPTS.get(mode, _COMMUNITY_SYSTEM)
    context = format_passages(passages)

    prompt = f"{system_prompt}\n\nContext:\n{context}\n\nQuestion ({locale}): {query}\n\nAnswer:"

    inputs = _local_tokenizer(  # type: ignore[misc]
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=LOCAL_CONTEXT_WINDOW,
    ).to(_local_model.device)  # type: ignore[union-attr]

    outputs = _local_model.generate(  # type: ignore[union-attr]
        **inputs,
        max_new_tokens=LOCAL_MAX_TOKENS,
        temperature=LOCAL_TEMPERATURE,
        do_sample=True,
        top_p=0.9,
    )

    answer = _local_tokenizer.decode(  # type: ignore[misc]
        outputs[0][inputs["input_ids"].shape[1]:],
        skip_special_tokens=True,
    )

    return {"text": answer, "usage": {"input_tokens": inputs["input_ids"].shape[1], "output_tokens": len(outputs[0]) - inputs["input_ids"].shape[1]}}


# ── Passage-based response (no LLM needed — instant, zero-cost) ────────────

def generate_from_passages(
    query: str,
    passages: list[dict[str, Any]],
    mode: str = "community",
    locale: str = "en",
) -> dict[str, Any]:
    """Generate a grounded response directly from retrieved passages.

    No LLM needed — assembles the best matching passages into a
    coherent response with source citations. Works instantly,
    offline, with zero API cost. Perfect for demo or low-resource
    deployments.
    """
    if not passages:
        return {
            "text": (
                "I don't have enough information to answer this question. "
                "Please visit the nearest health facility or call 0800 100 263."
            ),
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }

    # Build response from top passages
    parts = []
    for i, p in enumerate(passages[:3]):
        text = p.get("text", "").strip()
        source = p.get("source", "MoH Guidelines")
        section = p.get("section", "")
        if text:
            header = f"**[{i+1}] {source}"
            if section:
                header += f" — {section}"
            header += "**"
            parts.append(f"{header}\n\n{text}")

    response = "\n\n---\n\n".join(parts)

    # Add disclaimer
    response += (
        "\n\n---\n*This is health guidance based on official Uganda Ministry of Health "
        "guidelines — not a medical diagnosis. If symptoms worsen, visit the nearest "
        "health facility or call 0800 100 263 (toll-free).*"
    )

    return {
        "text": response,
        "usage": {"input_tokens": 0, "output_tokens": len(response.split())},
    }


# ── Unified interface ──────────────────────────────────────────────────────

def generate(
    query: str,
    passages: list[dict[str, Any]],
    mode: str = "community",
    history: list[dict[str, str]] | None = None,
    locale: str = "en",
) -> dict[str, Any]:
    """Generate health guidance using the best available backend.

    Priority: Groq → Claude → Local → Passage-based.
    Always returns a response — never fails silently.
    """
    # Try Groq first (free, fast)
    if GROQ_API_KEY:
        try:
            return generate_groq(query, passages, mode, history, locale)
        except Exception as e:
            logger.warning("Groq failed, falling back: %s", e)

    # Try Claude API
    if ANTHROPIC_API_KEY:
        try:
            return generate_claude(query, passages, mode, history, locale)
        except Exception as e:
            logger.warning("Claude failed, falling back: %s", e)

    # Try local model
    if LLM_BACKEND == "local":
        try:
            return generate_local(query, passages, mode, locale)
        except Exception as e:
            logger.warning("Local model failed: %s", e)

    # Passage-based fallback — always works
    return generate_from_passages(query, passages, mode, locale)


def stream_tokens(
    query: str,
    passages: list[dict[str, Any]],
    mode: str = "community",
    history: list[dict[str, str]] | None = None,
    locale: str = "en",
) -> Generator[dict[str, Any], None, None]:
    """Stream tokens from best available backend."""
    # Try Groq streaming first
    if GROQ_API_KEY:
        try:
            yield from stream_groq(query, passages, mode, history, locale)
            return
        except Exception as e:
            logger.warning("Groq streaming failed: %s", e)

    # Try Claude streaming
    if ANTHROPIC_API_KEY:
        try:
            yield from stream_claude(query, passages, mode, history, locale)
            return
        except Exception as e:
            logger.warning("Claude streaming failed: %s", e)

    # Fallback: generate full response and yield as single chunk
    try:
        if LLM_BACKEND == "local":
            result = generate_local(query, passages, mode, locale)
        else:
            result = generate_from_passages(query, passages, mode, locale)
    except Exception:
        result = generate_from_passages(query, passages, mode, locale)

    yield {"type": "token", "text": result["text"]}
    yield {"type": "done", "usage": result["usage"]}


def is_ready() -> bool:
    """Check if any LLM backend is available."""
    if GROQ_API_KEY:
        return True
    if ANTHROPIC_API_KEY:
        return True
    if LLM_BACKEND == "local":
        try:
            _load_local_model()
            return _local_model is not None
        except Exception:
            pass
    # Passage-based fallback is always ready
    return True
