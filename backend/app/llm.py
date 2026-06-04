"""Musawo AI — LLM integration layer.

Supports multiple backends (priority order):
1. Gemini API (default — gemini-2.0-flash via OpenAI-compatible API)
2. Groq API (fallback — llama-3.3-70b / qwen3-32b via OpenAI-compatible API)
3. Local model (GGUF / transformers, offline)
4. Passage-based (zero-cost, instant, no LLM needed)

Health-specific system prompts for each mode (VHT, Maternal, Community).
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Generator

logger = logging.getLogger("musawo.llm")

# ── Token estimation (lightweight, no external deps) ──────────────────────

def estimate_tokens(text: str) -> int:
    """Estimate token count using the ~4 chars per token heuristic.

    More accurate than word count, sufficient for budget enforcement.
    For exact counting, use tiktoken (but it's heavy for deployment).
    """
    return max(len(text) // 4, 1)


def truncate_history_to_budget(
    messages: list[dict],
    max_tokens: int,
    system_tokens: int = 0,
    passage_tokens: int = 0,
) -> list[dict]:
    """Truncate conversation history to fit within token budget.

    Keeps the most recent messages, dropping oldest first.
    Reserves space for system prompt, passages, and generation.
    """
    available = max_tokens - system_tokens - passage_tokens - 500  # Reserve 500 for response
    if available <= 0:
        return []

    result = []
    total = 0
    for msg in reversed(messages):
        msg_tokens = estimate_tokens(msg.get("content", ""))
        if total + msg_tokens > available:
            break
        result.insert(0, msg)
        total += msg_tokens
    return result


# ── Config (centralized in app.config) ──────────────────────────────────────

from .config import settings

LLM_BACKEND = settings.llm_backend  # "gemini" | "groq" | "local" | "passages"

# Gemini (default — OpenAI-compatible endpoint)
GEMINI_API_KEY = settings.gemini_api_key
GEMINI_MODEL = settings.gemini_model
GEMINI_MAX_TOKENS = settings.gemini_max_tokens
GEMINI_TEMPERATURE = settings.gemini_temperature

# Groq (free tier, OpenAI-compatible)
GROQ_API_KEY = settings.groq_api_key
GROQ_MODEL = settings.groq_model
GROQ_MAX_TOKENS = settings.groq_max_tokens
GROQ_TEMPERATURE = settings.groq_temperature

# Local model (offline fallback)
LOCAL_MODEL = settings.llm_model
LOCAL_CONTEXT_WINDOW = settings.llm_context_window
LOCAL_MAX_TOKENS = settings.llm_max_tokens
LOCAL_TEMPERATURE = settings.llm_temperature
LOCAL_DEVICE = settings.llm_device

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
- Do NOT use markdown tables (no "| column | column |" syntax) — they do not fit
  the small phone screens used in the community. To compare two or more things,
  give each its own ## sub-heading with bullets, OR use one bullet per feature,
  e.g. "- Onset: Typhoid is gradual; Malaria is sudden." Never use the pipe
  character (|) to lay information out in rows or columns.
- When clinically helpful, include a diagram reference using ::diagram[key] syntax.
  Available diagrams: danger_signs, ors_preparation, handwashing, breathing_count,
  breastfeeding, immunization_schedule, dehydration_check, birth_preparedness,
  malaria_rdt, fever_assessment. Use at most ONE per response, and only when relevant.

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
9. When the context contains step-by-step procedures, numbered steps, or
   treatment instructions, reproduce them fully — do NOT summarize procedures
   into vague advice.
10. Always include phone numbers, clinic URLs, and dosage information exactly
    as they appear in the context.
11. For emergencies, always include the health hotline: 0800 100 263.

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

# ── Locale-specific prompt additions ──────────────────────────────────────
# Injected into the user message when locale is not English, giving the LLM
# explicit instructions and local terminology examples.

_LOCALE_INSTRUCTIONS: dict[str, str] = {
    "lg": """LANGUAGE INSTRUCTION: The user is writing in Luganda. You MUST respond entirely in Luganda.
Use simple, clear Luganda that a village community member can understand.
Use English medical terms in parentheses for clarity, e.g., "omusujja (fever)".
Common Luganda health terms to use:
- omusujja = fever, omutwe = headache, ekiddukaano = diarrhoea
- okufuuwa = cough, okusesema = vomiting, okulumwa = pain
- olubuto = pregnancy, okuzaala = delivery, omwana = child
- eddagala = medicine, ddwaliro = hospital/clinic, omusawo = doctor
- obubonero = signs/symptoms, okuyonsa = breastfeeding
- amazzi = water/fluids, omusaayi = blood, sukaari = diabetes
- "Genda mu ddwaliro amangu" = Go to the hospital immediately
- "Yita ku simu 0800 100 263" = Call 0800 100 263
Keep section headers in Luganda: ## Okulambulula (Assessment), ## Okuyamba (Guidance), ## Lwe Wetaaga Okugenda mu Ddwaliro (When to Refer).""",

    "nyn": """LANGUAGE INSTRUCTION: The user is writing in Runyankole. You MUST respond entirely in Runyankole.
Use simple, clear Runyankole that a community member can understand.
Use English medical terms in parentheses for clarity, e.g., "omushuija (fever)".
Common Runyankole health terms to use:
- omushuija = fever, omutwe = headache, okushaarira = diarrhoea
- okukora = cough, okushuuha = vomiting, okubabara = pain
- enda = pregnancy, okuzaara = delivery, omwana = child
- eddagara = medicine, irwariro = hospital/clinic, omusawo = doctor
- obubonero = signs/symptoms, okugonza = breastfeeding
- amazi = water/fluids, eshagama = blood, shukaari = diabetes
- "Genda omu rwariro hati" = Go to the hospital now
- "Koroha 0800 100 263" = Call 0800 100 263
Keep section headers in Runyankole: ## Okwebaza (Assessment), ## Okuyamba (Guidance), ## Norikwetaaga Okugenda Omu Rwariro (When to Refer).""",

    "sw": """LANGUAGE INSTRUCTION: The user is writing in Swahili. You MUST respond entirely in Swahili.
Use simple, clear Swahili that a community member can understand.
Use English medical terms in parentheses for clarity, e.g., "homa (fever)".
Common Swahili health terms to use:
- homa = fever, kichwa = headache, kuharisha = diarrhoea
- kikohozi = cough, kutapika = vomiting, maumivu = pain
- mimba = pregnancy, kuzaa = delivery, mtoto = child
- dawa = medicine, hospitali = hospital, daktari = doctor
- dalili = symptoms, kunyonyesha = breastfeeding
- maji = water/fluids, damu = blood, kisukari = diabetes
- "Nenda hospitali haraka" = Go to the hospital immediately
- "Piga simu 0800 100 263" = Call 0800 100 263
Keep section headers in Swahili: ## Tathmini (Assessment), ## Mwongozo (Guidance), ## Wakati wa Kwenda Hospitali (When to Refer).""",
}


def _get_system_prompt(mode: str, locale: str) -> str:
    """Get mode system prompt with locale-specific additions."""
    base = SYSTEM_PROMPTS.get(mode, _COMMUNITY_SYSTEM)
    locale_addition = _LOCALE_INSTRUCTIONS.get(locale, "")
    if locale_addition:
        return f"{base}\n\n{locale_addition}"
    return base


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
    system_prompt = _get_system_prompt(mode, locale)
    context = format_passages(passages)

    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    # Token budget enforcement — prevent context overflow
    sys_tokens = estimate_tokens(system_prompt)
    ctx_tokens = estimate_tokens(context)
    user_msg = f"Context from official health guidelines:\n{context}\n\nUser question ({locale}): {query}\n\nRespond directly to the patient/VHT. Do NOT show your thinking process."
    if history:
        budgeted = truncate_history_to_budget(
            history[-10:],
            max_tokens=8192,  # Groq context window
            system_tokens=sys_tokens,
            passage_tokens=ctx_tokens + estimate_tokens(query),
        )
        for turn in budgeted:
            messages.append(turn)
    messages.append({
        "role": "user",
        "content": user_msg,
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
    system_prompt = _get_system_prompt(mode, locale)
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


# ── Gemini backend (default — OpenAI-compatible endpoint) ──────────────────

_gemini_client = None
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from openai import OpenAI
        _gemini_client = OpenAI(api_key=GEMINI_API_KEY, base_url=_GEMINI_BASE_URL)
    return _gemini_client


def generate_gemini(
    query: str,
    passages: list[dict[str, Any]],
    mode: str,
    history: list[dict[str, str]] | None = None,
    locale: str = "en",
) -> dict[str, Any]:
    """Generate via Google Gemini Flash (OpenAI-compatible API). Primary backend."""
    client = _get_gemini_client()
    system_prompt = _get_system_prompt(mode, locale)
    context = format_passages(passages)

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if history:
        budgeted = truncate_history_to_budget(
            history[-10:],
            max_tokens=30000,  # Gemini Flash has a very large context window
            system_tokens=estimate_tokens(system_prompt),
            passage_tokens=estimate_tokens(context) + estimate_tokens(query),
        )
        messages.extend(budgeted)
    messages.append({
        "role": "user",
        "content": f"Context from official health guidelines:\n{context}\n\nUser question ({locale}): {query}\n\nRespond directly to the patient/VHT.",
    })

    try:
        response = client.chat.completions.create(
            model=GEMINI_MODEL,
            messages=messages,
            max_tokens=GEMINI_MAX_TOKENS,
            temperature=GEMINI_TEMPERATURE,
        )
        answer = (response.choices[0].message.content or "").strip()
        return {
            "text": answer,
            "usage": {
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        }
    except Exception as e:
        logger.error("Gemini API error: %s", e)
        raise


def stream_gemini(
    query: str,
    passages: list[dict[str, Any]],
    mode: str,
    history: list[dict[str, str]] | None = None,
    locale: str = "en",
) -> Generator[dict[str, Any], None, None]:
    """Streaming generation via Gemini (OpenAI-compatible)."""
    client = _get_gemini_client()
    system_prompt = _get_system_prompt(mode, locale)
    context = format_passages(passages)

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if history:
        for turn in history[-10:]:
            messages.append(turn)
    messages.append({
        "role": "user",
        "content": f"Context from official health guidelines:\n{context}\n\nUser question ({locale}): {query}\n\nRespond directly.",
    })

    try:
        stream = client.chat.completions.create(
            model=GEMINI_MODEL,
            messages=messages,
            max_tokens=GEMINI_MAX_TOKENS,
            temperature=GEMINI_TEMPERATURE,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield {"type": "token", "text": delta.content}
        yield {"type": "done", "usage": {}}
    except Exception as e:
        logger.error("Gemini streaming error: %s", e)
        raise


# ── Local model backend (offline fallback) ─────────────────────────────────
#
# Smart fallback chain for local inference:
# 1. GGUF via llama-cpp-python (4-6GB RAM, fastest CPU inference)
# 2. Quantized via BitsAndBytes (8-bit/4-bit, needs GPU)
# 3. Full-precision via transformers (16GB+ VRAM or 32GB RAM)
#
# Recommended models (Apache 2.0, production-ready):
# - GGUF: Qwen/Qwen3-8B-GGUF (Q5_K_M variant, ~5GB)
# - HF: Qwen/Qwen3-8B with 4-bit BnB quantization (~4GB VRAM)

_local_model = None
_local_tokenizer = None
_local_backend = None  # "gguf" | "bnb4" | "bnb8" | "transformers"

# GGUF model path (set via env for llama.cpp backend)
GGUF_MODEL_PATH = settings.gguf_model_path
LOCAL_GPU_LAYERS = settings.local_gpu_layers  # For GGUF: layers on GPU

# LoRA adapter path — fine-tuned Luganda adapter merged at load time
LORA_ADAPTER_PATH = settings.lora_adapter_path or None


def _load_local_model():
    """Smart local model loading: tries GGUF → 4-bit → 8-bit → full precision."""
    global _local_model, _local_tokenizer, _local_backend
    if _local_model is not None:
        return

    # Strategy 1: GGUF via llama-cpp-python (best for CPU, lowest memory)
    if GGUF_MODEL_PATH:
        try:
            from llama_cpp import Llama
            logger.info("Loading GGUF model: %s (gpu_layers=%d)", GGUF_MODEL_PATH, LOCAL_GPU_LAYERS)
            _local_model = Llama(
                model_path=GGUF_MODEL_PATH,
                n_ctx=LOCAL_CONTEXT_WINDOW,
                n_gpu_layers=LOCAL_GPU_LAYERS,
                verbose=False,
            )
            _local_backend = "gguf"
            logger.info("Local model ready (backend=gguf, ctx=%d)", LOCAL_CONTEXT_WINDOW)
            return
        except ImportError:
            logger.info("llama-cpp-python not installed, trying transformers")
        except Exception as e:
            logger.warning("GGUF loading failed: %s", e)

    # Strategy 2: 4-bit quantized via BitsAndBytes (GPU, ~4GB VRAM)
    try:
        import torch
        if torch.cuda.is_available():
            try:
                from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
                logger.info("Loading 4-bit quantized: %s", LOCAL_MODEL)
                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_quant_type="nf4",
                )
                _local_tokenizer = AutoTokenizer.from_pretrained(LOCAL_MODEL)
                _local_model = AutoModelForCausalLM.from_pretrained(
                    LOCAL_MODEL,
                    quantization_config=bnb_config,
                    device_map="auto",
                    trust_remote_code=False,
                )
                _local_backend = "bnb4"
                logger.info("Local model ready (backend=bnb4, device=cuda)")
                return
            except ImportError:
                logger.info("bitsandbytes not installed, trying full precision")
            except Exception as e:
                logger.warning("4-bit loading failed: %s", e)
    except ImportError:
        pass

    # Strategy 3: Full-precision via transformers (fallback, needs most memory)
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        logger.info("Loading full-precision model: %s", LOCAL_MODEL)
        _local_tokenizer = AutoTokenizer.from_pretrained(LOCAL_MODEL)
        _local_model = AutoModelForCausalLM.from_pretrained(
            LOCAL_MODEL,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map=LOCAL_DEVICE,
            trust_remote_code=False,
        )
        _local_backend = "transformers"
        logger.info("Local model ready (backend=transformers, device=%s)", LOCAL_DEVICE)
    except Exception as e:
        logger.error("All local model loading failed: %s", e)
        raise

    # Load fine-tuned LoRA adapter if configured
    if _local_backend in ("bnb4", "transformers") and LORA_ADAPTER_PATH and os.path.isdir(LORA_ADAPTER_PATH):
        try:
            from peft import PeftModel
            logger.info("Loading LoRA adapter from %s", LORA_ADAPTER_PATH)
            _local_model = PeftModel.from_pretrained(_local_model, LORA_ADAPTER_PATH)
            _local_model = _local_model.merge_and_unload()
            logger.info("LoRA adapter merged successfully")
        except ImportError:
            logger.warning("peft not installed; skipping LoRA adapter")
        except Exception:
            logger.exception("Failed to load LoRA adapter from %s", LORA_ADAPTER_PATH)


def generate_local(
    query: str,
    passages: list[dict[str, Any]],
    mode: str,
    locale: str = "en",
) -> dict[str, Any]:
    """Generate using local model (GGUF, quantized, or full precision)."""
    _load_local_model()

    system_prompt = _get_system_prompt(mode, locale)
    context = format_passages(passages)

    # GGUF backend (llama.cpp) — uses chat completion API
    if _local_backend == "gguf":
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion ({locale}): {query}"},
        ]
        result = _local_model.create_chat_completion(  # type: ignore
            messages=messages,
            max_tokens=LOCAL_MAX_TOKENS,
            temperature=LOCAL_TEMPERATURE,
            top_p=0.9,
        )
        answer = result["choices"][0]["message"]["content"]  # type: ignore
        usage = result.get("usage", {})
        # Strip Qwen3 thinking blocks if present
        import re as _re
        answer = _re.sub(r"<think>.*?</think>", "", answer, flags=_re.DOTALL).strip()
        return {"text": answer, "usage": usage}

    # Transformers backend (full or quantized)
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
    # Strip thinking blocks
    import re as _re
    answer = _re.sub(r"<think>.*?</think>", "", answer, flags=_re.DOTALL).strip()

    return {
        "text": answer,
        "usage": {
            "input_tokens": inputs["input_ids"].shape[1],
            "output_tokens": len(outputs[0]) - inputs["input_ids"].shape[1],
            "backend": _local_backend,
        },
    }


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
    # Locale-aware template strings
    _templates = {
        "lg": {
            "no_info": "Sirina bukimu bumala okukuddamu ekibuuzo kino. Genda mu ddwaliro erisinga okuba okumpi oba yita ku simu 0800 100 263.",
            "header": "## Okuyamba\n\nOkusinziira ku biragiro by'obulamu eby'ofiisi bya Uganda:\n\n",
            "refer_header": "## Lwe Wetaaga Okugenda mu Ddwaliro\n\n",
            "refer_body": "- Obubonero bwe bweyongera oba tokakaanya, **genda mu ddwaliro amangu ddala**\n",
            "hotline": "- Esimu y'amangu: **0800 100 263** (ya bwereere, essaawa zonna)\n\n",
            "disclaimer": "---\n*Buno bubaka bw'obuyambi bw'obulamu kyokka — si bulamu bwa musawo. Ennyiriri: Biragiro by'Obulamu bya Gavumenti ya Uganda.*",
        },
        "nyn": {
            "no_info": "Tinyine buhangwa buhikire okukusubiza ekibuuzo kino. Genda omu rwariro erisinga okuba hakuuhi nari koroha 0800 100 263.",
            "header": "## Okuyamba\n\nOkurugirira ahamateeka g'obuhaise ga Uganda:\n\n",
            "refer_header": "## Norikwetaaga Okugenda Omu Rwariro\n\n",
            "refer_body": "- Obubonero nibweyongera nari otarikumanya, **genda omu rwariro hati nyowe**\n",
            "hotline": "- Esimu y'amaani: **0800 100 263** (ya bure, obudde bwona)\n\n",
            "disclaimer": "---\n*Obu ni buhangwa bw'obuhaise obukuru — tiburikuba obutibu. Entururo: Amateeka g'obuhaise ga Gavumenti ya Uganda.*",
        },
        "sw": {
            "no_info": "Sina taarifa za kutosha kujibu swali hili kwa uhakika. Tafadhali nenda hospitali ya karibu au piga simu 0800 100 263.",
            "header": "## Mwongozo\n\nKulingana na miongozo rasmi ya afya ya Uganda:\n\n",
            "refer_header": "## Wakati wa Kwenda Hospitali\n\n",
            "refer_body": "- Dalili zikizidi au huna uhakika, **nenda hospitali haraka**\n",
            "hotline": "- Simu ya dharura: **0800 100 263** (bila malipo, masaa 24)\n\n",
            "disclaimer": "---\n*Hii ni mwongozo wa afya tu — si uchunguzi wa daktari. Chanzo: Miongozo rasmi ya Wizara ya Afya ya Uganda.*",
        },
        "en": {
            "no_info": "I don't have enough information to answer this question. Please visit the nearest health facility or call 0800 100 263.",
            "header": "## Guidance\n\nBased on the official Uganda health guidelines:\n\n",
            "refer_header": "## When to Refer\n\n",
            "refer_body": "- If symptoms worsen or you are unsure, **visit the nearest health facility immediately**\n",
            "hotline": "- Emergency hotline: **0800 100 263** (toll-free, 24/7)\n\n",
            "disclaimer": "---\n*This is health guidance only — not a medical diagnosis. Source: Uganda Ministry of Health official guidelines.*",
        },
    }
    t = _templates.get(locale, _templates["en"])

    if not passages:
        return {
            "text": t["no_info"],
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }

    # Build structured response from passages
    response = t["header"]

    for i, p in enumerate(passages[:3]):
        text = p.get("text", "").strip()
        source = p.get("source", "MoH Guidelines")
        section = p.get("section", "")
        if not text:
            continue

        source_label = f"**[{i+1}] {source}"
        if section:
            source_label += f" — {section}"
        source_label += "**\n\n"

        import re as _re
        sentences = _re.split(r'(?<=[.!:])\s+(?=[A-Z(])', text)
        formatted_lines = []
        for sent in sentences[:8]:
            sent = sent.strip()
            if not sent:
                continue
            for term in ["REFER", "IMMEDIATELY", "DANGER", "DO NOT", "MUST"]:
                sent = sent.replace(term, f"**{term}**")
            formatted_lines.append(f"- {sent}")

        response += source_label + "\n".join(formatted_lines) + "\n\n"

    response += t["refer_header"]
    response += t["refer_body"]
    response += t["hotline"]
    response += t["disclaimer"]

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

    Priority: Gemini → Groq → Local → Passage-based.
    Always returns a response — never fails silently.
    """
    # Try Gemini first (default — fast, large context)
    if GEMINI_API_KEY:
        try:
            return generate_gemini(query, passages, mode, history, locale)
        except Exception as e:
            logger.warning("Gemini failed, falling back: %s", e)

    # Fallback to Groq (free, fast)
    if GROQ_API_KEY:
        try:
            return generate_groq(query, passages, mode, history, locale)
        except Exception as e:
            logger.warning("Groq failed, falling back: %s", e)

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
    # Try Gemini streaming first (default)
    if GEMINI_API_KEY:
        try:
            yield from stream_gemini(query, passages, mode, history, locale)
            return
        except Exception as e:
            logger.warning("Gemini streaming failed: %s", e)

    # Fallback to Groq streaming
    if GROQ_API_KEY:
        try:
            yield from stream_groq(query, passages, mode, history, locale)
            return
        except Exception as e:
            logger.warning("Groq streaming failed: %s", e)

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
    if GEMINI_API_KEY:
        return True
    if GROQ_API_KEY:
        return True
    if LLM_BACKEND == "local":
        try:
            _load_local_model()
            return _local_model is not None
        except Exception:
            pass
    # Passage-based fallback is always ready
    return True
