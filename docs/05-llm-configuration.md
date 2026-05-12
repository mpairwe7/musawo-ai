# 5. LLM Configuration — Musawo AI

## Fallback Chain

```
Groq (free, 500 tok/s) → Claude API → Local Qwen3 → Passage-based
```

Priority: try each in order, never fail silently.

## Groq (Primary)

| Setting | Value |
|---------|-------|
| Model | `llama-3.3-70b-versatile` |
| Max tokens | 4096 |
| Temperature | 0.3 |
| API | OpenAI-compatible (`api.groq.com/openai/v1`) |
| Cost | Free tier |

## Claude (Secondary)

| Setting | Value |
|---------|-------|
| Model | `claude-sonnet-4-6-20250514` |
| Prompt caching | Enabled (ephemeral cache control) |
| Extended thinking | Enabled for complex medical queries |
| Thinking budget | 10000 tokens |

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
