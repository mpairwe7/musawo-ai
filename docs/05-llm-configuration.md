# 5. LLM Configuration — Musawo AI

## Fallback Chain

```
Gemini Flash (default) → Groq (free, 500 tok/s) → Local Qwen3 → Passage-based
```

Priority: try each in order, never fail silently. Each tier fails fast (short
connect timeout, no retries) so a blocked path demotes in seconds. Claude /
Anthropic has been removed.

## Gemini (Default)

| Setting | Value |
|---------|-------|
| Model | `gemini-2.5-flash` (`GEMINI_MODEL`) |
| API | OpenAI-compatible (`generativelanguage.googleapis.com/v1beta/openai`) |
| Selected when | `GEMINI_API_KEY` is set |

**Cloudflare AI Gateway:** on firewalled pods (RENU) where Google IPs are
unreachable, set `CF_ACCOUNT_ID` + `CF_AI_GATEWAY` (+ `CF_AIG_TOKEN`) and Gemini
is routed through `gateway.ai.cloudflare.com/.../compat` over Cloudflare's edge.
See [`egress-cloudflare-gateway.md`](egress-cloudflare-gateway.md).

## Groq (Fallback)

| Setting | Value |
|---------|-------|
| Model | `llama-3.3-70b-versatile` |
| Max tokens | 4096 |
| Temperature | 0.3 |
| API | OpenAI-compatible (`api.groq.com/openai/v1`) |
| Cost | Free tier |

## Local Qwen3 (Offline)

Loading strategy: GGUF → 4-bit BnB → 8-bit BnB → Full precision

| Backend | Memory | Speed |
|---------|--------|-------|
| GGUF (llama.cpp) | ~4GB | CPU: ~10 tok/s |
| BNB4 (bitsandbytes) | ~4GB VRAM | GPU: ~30 tok/s |
| Transformers (FP16) | ~16GB | GPU: ~50 tok/s |

## Passage-Based (Always Available)

Extracts key phrases from retrieved passages without LLM. Returns safe fallback: "Visit your nearest health facility or call 0800 100 263."

## System Prompt

Mode-specific prompts with:
- Role definition (VHT assistant, maternal advisor, community guide)
- Uganda MoH guideline grounding
- Citation format ([1], [2] from passages)
- Multilingual locale instructions (Luganda, Runyankole, Swahili)
- Safety: "Do NOT diagnose. Always recommend facility visit for serious symptoms."
