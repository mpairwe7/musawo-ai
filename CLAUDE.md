# Musawo AI — Architecture Decisions

## Overview

Musawo AI is a community health navigator for rural Uganda, forked from
the URA Chatbot codebase and heavily adapted for health-tech. It serves
three modes: VHT Triage, Maternal Care, and Community Health.

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│              Next.js 16 PWA (Grok-inspired UI)            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │VHT Mode  │  │Maternal  │  │Community │  ← Mode cards  │
│  └──────────┘  └──────────┘  └──────────┘               │
│  ┌──────────────────────────────────────────┐            │
│  │   Chat (markdown, collapse, avatars,     │            │
│  │   timestamps, ## structured responses)   │            │
│  └──────────────────────────────────────────┘            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │IndexedDB │  │ServiceWkr│  │VoiceI/O  │  ← Offline    │
│  └──────────┘  └──────────┘  └──────────┘               │
└───────────────────────────┬──────────────────────────────┘
                            │ /api proxy (SSE + sync)
┌───────────────────────────▼──────────────────────────────┐
│                    FastAPI Backend                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │InputGuard│→ │Supervisor│→ │Retriever │               │
│  └──────────┘  └──────────┘  └──────────┘               │
│       │           │   │            │                      │
│       │     mode route │     Qdrant dense                 │
│       │     + red-flag │    (bge-m3 CPU)                  │
│       │       detect   │      + cross-mode                │
│       │                │       fallback                   │
│  ┌──────────┐  ┌───────▼──┐  ┌──────────┐               │
│  │Guardrails│← │  LLM     │← │Grounding │               │
│  │(output)  │  │ Groq     │  │(faithful)│               │
│  └──────────┘  │ →Claude  │  └──────────┘               │
│                │ →Passage  │                              │
│                └──────────┘                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │ Triage   │  │ Twilio   │  │Prometheus│               │
│  │ Agent    │  │ SMS/USSD │  │ /metrics │               │
│  └──────────┘  └──────────┘  └──────────┘               │
└──────────────────────────────────────────────────────────┘
```

## Key Decisions

### 1. Three-Tier LLM Fallback (Groq → Claude → Passage-based)

- **Groq API** (primary): Free tier, ~500 tok/s. Uses Qwen3-32B or Llama-3.3-70B
  via OpenAI-compatible API. Produces structured ## Assessment / ## Guidance /
  ## When to Refer responses. Qwen3 thinking blocks auto-stripped.
- **Claude API** (secondary): If Groq rate-limited. Prompt caching reduces cost ~90%.
  Extended thinking for complex queries.
- **Passage-based** (always-available): Zero-cost, instant. Assembles retrieved
  passages into a response with source citations. Works offline with no API key.

The system **never fails silently** — if all LLMs are unavailable, passages are
served directly with the disclaimer.

### 2. Deep Conversation Context (10-Turn Window)

- Session history stored in a thread-safe `SessionStore` with per-session Lock
- Last 10 turn-pairs (20 messages) sent to the LLM on every request
- Enables multi-turn clinical discussions: "child has fever" → "also diarrhoea" →
  "should I refer?" — the LLM remembers the entire patient encounter
- Sessions persist via `session_id` in both frontend (`sessionStorage`) and backend
- 24-hour TTL, max 5000 concurrent sessions

### 3. Agentic iCCM Triage (VHT Mode)

- Stateful multi-step agent: INITIAL → DANGER_CHECK → ASSESS → CLASSIFY → TREAT_REFER
- Danger sign detection runs at EVERY phase via hard-coded regex (no LLM needed)
- If ANY danger sign found at ANY point → immediate REFER with pre-referral treatment
- iCCM decision tree: RDT-guided malaria, breathing-rate pneumonia, ORS+Zinc diarrhoea
- Agent asks follow-up questions: "Has the child had convulsions? Can they drink?"
- `/v1/triage` endpoint separate from `/v1/chat` — different UX in frontend

### 4. Cross-Mode Retrieval Fallback

- First search: mode-filtered (e.g., only `mode=vht` entries)
- If <2 results or all scores <0.3: search ALL modes unfiltered
- Ensures relevant clinical content is always found even if tagged differently
- Dense search via bge-m3 on CPU (no reranker — Qwen2-based reranker had
  uninitialized weights producing inflated 0.999 scores)

### 5. Grok-Inspired Chat UX

Inspired by Grok, ChatGPT, and Ada Health for a health-appropriate experience:

- **Markdown rendering**: `## Headers` as green-accented section dividers,
  **bold** drug names, bullet lists with styled dots, `code` for dosages
- **Collapsible messages**: Long responses get ▲/▼ toggle (important on mobile)
- **Role avatars**: Green "M" (Musawo), gray "Y" (You) — visual identity
- **Timestamps**: Every response shows HH:MM
- **Clear chat**: Trash icon in header with confirmation dialog
- **Empty state**: Gradient welcome with icon, title, subtitle
- **Typing indicator**: "Searching health guidelines..." with animated dots
- **Offline banner**: Prominent warning with emergency number
- **Triage card pinned above text**: CSS `order: -1` ensures severity visible first

### 6. Offline-First PWA

- **Service Worker**: Cache-first for app shell, network-first for API
- **IndexedDB**: Conversations, cached RAG responses, facility data, medication reminders
- **Background Sync**: Real implementation — SW reads from IndexedDB and POSTs
  queued messages to `/api/v1/chat` when connectivity returns
- **PWA Install Prompt**: `beforeinstallprompt` handler with Install/Dismiss UI

### 7. SMS/USSD Gateway (Twilio)

- **USSD menu tree**: `*384#` → VHT Triage → Fever/Cough/Diarrhoea/Danger Signs
  + Maternal Health → Danger Signs/Breastfeeding/Newborn/Family Planning
  + Emergency Contacts + Nearest Clinic
- **SMS webhook**: `/v1/sms/webhook` receives incoming SMS, detects danger-sign
  keywords, returns instant guidance. All messages ≤1600 chars (Twilio concat).
- **SMS send**: `/v1/sms/send?phone=+256...&message=...` via Twilio REST API

### 8. Never-Diagnose Guardrails

- System prompts explicitly prohibit diagnosis and prescription
- Confidence scoring: HIGH/MEDIUM/LOW badge on every response
- Abstention threshold: 0.05 (lowered from 0.15 to let LLM answer more with disclaimer)
- Mandatory disclaimer on every response
- Crisis escalation: suicide/self-harm → immediate hotline referral
- PII redaction: Uganda-specific (NIN, phone, HIV status, ART number)

## File Structure

```
backend/app/
  main.py         — FastAPI: chat, triage, facilities, USSD, SMS, metrics
  service.py      — HealthService: RAG pipeline + thread-safe sessions
  llm.py          — 3-tier LLM: Groq → Claude → Passage-based
  retriever.py    — Qdrant dense search (bge-m3 CPU) + keyword fallback
  guardrails.py   — OWASP LLM Top 10 input/output safety
  sms_gateway.py  — Twilio SMS + USSD menu tree
  metrics.py      — Prometheus counters/histograms/gauges
  models.py       — Pydantic schemas (ChatRequest, TriageResult, etc.)
  agents/
    triage_agent.py — Stateful iCCM triage (6 phases)
    supervisor.py   — Mode classifier + red-flag regex
    state.py        — RouteDecision dataclass

frontend/src/
  app/page.tsx        — Grok-inspired chat: empty state, panels, agentic toggle
  app/globals.css     — Design system: tokens, glass, responsive (320-1440px)
  components/
    ChatMessage.tsx   — Markdown renderer, collapse, avatars, timestamps, feedback
    ChatInput.tsx     — Voice input, forwarded ref, auto-resize
    ClinicFinder.tsx  — GPS + OSM map + Haversine + offline cache
    MaternalTracker   — Pregnancy week, milestones, danger signs
    MedicationReminders — IndexedDB CRUD
    SettingsPanel     — Cache management, about
    InstallPrompt     — PWA install banner
  lib/voiceOutput.ts  — TTS danger sign alerts (4 languages)
  lib/offlineDb.ts    — IndexedDB (5 stores)
  store/useChatStore  — Zustand + localStorage persistence
  hooks/useApi.ts     — TanStack Query + useAgenticTriage
```

## Conventions

- Commit messages: conventional commits (feat/fix/docs)
- Python: type hints, Ruff formatting
- TypeScript: strict mode
- CSS: design tokens in :root, semantic `--severity-*` colors, no Tailwind
- LLM responses: structured ## sections for consistent rendering
