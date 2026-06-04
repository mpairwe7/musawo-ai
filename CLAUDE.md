# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Musawo AI is a community health navigator for rural Uganda, forked from a URA Chatbot codebase and adapted for health-tech. It serves three modes: **VHT Triage**, **Maternal Care**, and **Community Health**. Stack: FastAPI backend + Next.js 16 PWA frontend + Qdrant for retrieval + Sunbird AI for Ugandan-language voice/translation.

## Request pipeline

Every `/v1/chat` and `/v1/chat/stream` request flows through this exact ordering in `backend/app/service.py` (`HealthService`):

```
InputGuard (i18n abstention, crisis detection, PII redaction)
   ↓
Supervisor (mode classifier + multilingual negation-aware red-flag scan)
   ↓
Retriever (Qdrant dense bge-m3 + keyword fallback; query expansion, severity boost, dual-search for non-English)
   ↓
LLM (6-tier fallback, see below)
   ↓
Guardrails (clinical safety gate on faithfulness, locale-aware disclaimers, audit log)
```

The system **never fails silently**: if every LLM tier is down, formatted retrieval passages are returned as the answer with a disclaimer. If faithfulness < `CLINICAL_SAFETY_THRESHOLD` (0.2), the response is gated or strongly warned, and escalation is auto-triggered.

`/v1/triage` bypasses the chat path and routes to the stateful agent in `backend/app/agents/triage_agent.py`.

## LLM fallback chain (6-tier, `backend/app/llm.py`)

In order of preference, each tier silently demotes on failure:

1. **Gemini API** — default. Tries the `GEMINI_MODELS` priority list (newest first: `gemini-3.5-flash` → `gemini-3.0-flash` → `gemini-2.5-flash`), using the first available and falling through on a "model not available" (404). On RENU it's routed via the Cloudflare AI Gateway. Set `GEMINI_API_KEY`.
2. **Groq API** — fallback, free tier (Qwen3-32B / Llama-3.3-70B). Token budget enforced to prevent context overflow.
3. **GGUF via llama-cpp-python** — CPU quantized (Q5_K_M, 4–6GB RAM). Enable by setting `GGUF_MODEL_PATH`.
4. **4-bit BitsAndBytes** — auto-detected if GPU available (~4GB VRAM, NF4).
5. **Full-precision transformers** — fallback when quant libs unavailable.
6. **Passage-based templates** — zero-cost, always-on, locale-aware (EN/LG/NYN/SW), offline-capable.

## Agentic triage state machine (`backend/app/agents/triage_agent.py`)

Phases: `INITIAL → DANGER_CHECK → ASSESS → CLASSIFY → TREAT_REFER`. Classifies 6 iCCM conditions: Malaria, Pneumonia, Diarrhoea, Measles, SAM, MAM.

Important invariants:
- Danger-sign regex runs at **every** phase (EN/LG/NYN/SW patterns).
- **Negation-aware**: any red-flag match preceded within 4 tokens by a negation word (`no`/`not`/`never`/`tewali`/`hakuna`/...) is skipped. The supervisor enforces the same rule — don't add new red-flag patterns without also covering negation.
- Info queries ("What is the ORS dosage?") are detected and answered from KB directly without entering the triage flow.
- Fast-track: if initial query has age + sufficient symptoms, danger check is skipped and CLASSIFY runs immediately.
- Dehydration severity maps to iCCM Plan A/B/C; MUAC values are extracted from text to grade SAM (<115mm) vs MAM.

## Retrieval gotchas (`backend/app/retriever.py`)

- **Query expansion** uses ~19 health-domain synonym clusters before encoding (e.g. "prevent malaria" → adds "mosquito net LLIN prevention"). Adding clusters affects all queries — bench against `tests/bench_eval.py`.
- **Stop words** (84-word EN list) are stripped only from the keyword-match path; dense embedding keeps the full query.
- **Severity weighting**: Red-flagged passages get +0.15, Yellow +0.05 score boost. Section-name token overlap adds +0.1/token.
- **LRU cache (200 entries)** returns **deep copies** — never mutate retrieved passage dicts in place, scores will leak across requests.
- **Cross-mode fallback**: if mode-filtered results < 2 or top score < 0.3, the retriever re-searches across all modes unfiltered.
- **Dual-search for non-English**: query is searched with both the Sunbird-translated English form **and** the original; results merged by best unique score.

## Sessions & context window

- `SessionStore` in `service.py` is thread-safe with per-session `Lock`.
- Last **10 turn-pairs (20 messages)** are sent to the LLM on every request — token-counted and truncated upstream.
- Sessions: 24h TTL, max 5000 concurrent; `session_id` round-trips between frontend `sessionStorage` and the backend.

## Voice (`backend/app/sunbird.py`, `voice_ws.py`, `voice_stream.py`)

Two fallback chains, both fail-soft to browser-native APIs:

| Layer | Cloud primary | Local primary | Local fallback | Browser fallback |
|-------|---------------|---------------|----------------|------------------|
| STT   | Sunbird API   | Parakeet TDT 0.6B | Moonshine 27M / faster-whisper / OpenAI Whisper | Web Speech API |
| TTS   | Sunbird (speaker IDs: LG #248, NYN #243, SW #246) | CosyVoice2-0.5B | edge-tts | `speechSynthesis` |

Sunbird auth uses `SUNBIRD_USERNAME` + `SUNBIRD_PASSWORD` (preferred over static `SUNBIRD_API_TOKEN`). Tokens auto-refresh every 6 days; all calls go through `_api_call()` which retries on 401. `langCode` mismatches between persona and TTS cause silent fallback to browser — keep `lg-UG` / `nyn-UG` / `sw-KE` codes intact.

## Internationalization

- Backend: `backend/app/i18n.py` (50+ keys, EN/LG/NYN/SW). All guardrail/abstention/disclaimer/triage strings flow through `t()`.
- Frontend: `frontend/src/lib/i18n.ts` (30+ keys).
- Locale-aware LLM system prompts include local-terminology glossary and section header translations.
- A 200+ entry health-term map provides offline retrieval enrichment when Sunbird translation is unavailable.

## API surface (`backend/app/main.py`)

`/v1/chat`, `/v1/chat/stream` (SSE), `/v1/triage`, `/v1/modes`, `/v1/facilities`, `/v1/facilities/nearby`, `/v1/ussd/callback`, `/v1/sms/send` (requires `x-api-key` + rate-limited 10/min), `/v1/sms/webhook` (Twilio signature verified), `/v1/session/{id}/history`, `/v1/feedback`, `/v1/emergency-contacts`, `/v1/voice/stt`, `/v1/voice/tts`, `/v1/translate`, `/v1/detect-language`, `/v1/voice/chat/stream` (WebSocket), `/health`, `/ready`, `/metrics` (Prometheus).

## Frontend conventions (`frontend/src/`)

- **No Tailwind.** Design system lives in `app/globals.css` as CSS custom properties (`--severity-*`, etc.). Glass effects and tokens defined in `:root`.
- LLM responses are rendered as markdown with `## section` headers treated as green-accented dividers. Keep this convention when changing LLM system prompts.
- **Diagrams**: Mermaid. The LLM emits a fenced ```mermaid block only when it genuinely clarifies (decision flow / referral pathway / steps); `components/MermaidDiagram.tsx` (lazy, `securityLevel: strict`, degrades to source on bad syntax) renders it inline. Contextual, never forced — at most one per response.
- **Lazy components**: `ClinicFinder`, `SettingsPanel`, `MedicationReminders`, `MermaidDiagram` are `React.lazy` — preserve `Suspense` boundaries when refactoring `app/page.tsx`.
- **State**: Zustand store at `store/useChatStore.ts` persists via `persist` middleware to localStorage; max 50 sessions.
- **Service worker** at `frontend/public/sw.js` does cache-first for app shell, network-first for `/api`, and a real Background Sync that drains queued chats from IndexedDB to `/api/v1/chat` on reconnect.

## Security & audit invariants

- **CORS**: wildcard only allowed when `APP_ENV != production`.
- **Twilio webhook**: `X-Twilio-Signature` is verified — don't bypass when testing.
- **Audio uploads** capped at `MAX_AUDIO_SIZE` (10MB default).
- **Audit trail**: every health-guidance interaction is appended to `AUDIT_LOG_PATH` (JSONL: session_id, query, answer_preview, confidence, faithfulness, escalation, triage_severity, citation count). Don't bypass this on new endpoints that return clinical content.
- **PII redaction** is Uganda-specific (NIN, phone, HIV status, ART number patterns) — pattern changes need test coverage in `tests/test_guardrails.py`.

## Key environment variables

```bash
# LLM (Gemini default, Groq fallback — set at least one)
GEMINI_API_KEY=
GROQ_API_KEY=
GGUF_MODEL_PATH=             # Enables tier 3
LOCAL_GPU_LAYERS=0           # GPU layers for GGUF

# Sunbird (prefer username/password for auto-refresh)
SUNBIRD_USERNAME=
SUNBIRD_PASSWORD=
SUNBIRD_API_TOKEN=           # static fallback

# Retrieval
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=musawo_health_kb
DENSE_MODEL=BAAI/bge-m3

# Safety thresholds
CLINICAL_SAFETY_THRESHOLD=0.2
ABSTENTION_THRESHOLD=0.05
GROUNDING_THRESHOLD=0.3
AUDIT_LOG_PATH=/tmp/musawo_audit.jsonl

# SMS
SMS_API_KEY=
TWILIO_AUTH_TOKEN=

# Runtime
APP_ENV=production           # strict CORS
WORKERS=2
MAX_AUDIO_SIZE=10485760
```

`.env.example` is the source of truth for the full list.

## Commands

### Backend

```bash
cd backend && pip install -r requirements.txt

# Dev server (Qdrant must be reachable)
GROQ_API_KEY=... SUNBIRD_USERNAME=... SUNBIRD_PASSWORD=... \
QDRANT_URL=http://localhost:6333 \
uvicorn app.main:app --port 8888 --reload

# Tests
python -m pytest tests/ -v
python -m pytest tests/test_service.py -v
python -m pytest tests/test_retriever.py::TestHybridRetrieverFallback::test_keyword_fallback_when_not_ready -v

# Benchmark suite (requires running backend at $API_URL)
python -m tests.bench_eval

# Format & lint
ruff format app/ tests/
ruff check app/ tests/
```

### Frontend

```bash
cd frontend && npm install

# Dev (talks to backend via INTERNAL_API_URL proxy)
INTERNAL_API_URL=http://localhost:8888 npx next dev --port 3200

npm run build
npm run test            # vitest single run
npm run test:watch
npm run test:coverage
npx tsc --noEmit        # typecheck
npm run lint            # eslint
```

### Docker & ops

```bash
docker compose up -d
docker compose --profile monitoring up -d   # + Prometheus/Grafana
docker compose build api frontend && docker compose up -d
docker compose logs -f api

./scripts/reindex.sh           # rebuild Qdrant index from knowledge-base/
./scripts/reindex.sh --check   # health check only
./scripts/demo-seed.sh         # full pre-demo smoke test
```

## Knowledge base

20 JSON files under `knowledge-base/` (~203 clinical entries) covering iCCM, maternal/neonatal, infectious disease, immunization, family planning, HIV/TB, WASH, first aid, nutrition, mental health, emergencies, facilities, and community symptom protocols. The Qdrant collection is rebuilt by `./scripts/reindex.sh` — entry-schema changes must be reflected in `backend/app/indexer.py`.

## Conventions

- **Commit messages**: conventional commits (`feat:`/`fix:`/`docs:`).
- **Python**: type hints, Ruff-formatted.
- **TypeScript**: strict mode.
- **CSS**: design tokens in `:root`, semantic `--severity-*` colors, no Tailwind.
- **LLM prompts**: keep `## section` headers + `::diagram[key]` references in sync with the renderer.
