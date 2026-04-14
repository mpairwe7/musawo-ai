# Musawo AI — Architecture Decisions

## Overview

Musawo AI is a community health navigator for rural Uganda, forked from
the URA Chatbot codebase and heavily adapted for health-tech. It serves
three modes: VHT Triage, Maternal Care, and Community Health.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Next.js 16 PWA                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │VHT Mode  │  │Maternal  │  │Community │  ← Mode cards │
│  └──────────┘  └──────────┘  └──────────┘              │
│  ┌─────────────────────────────────────────┐            │
│  │         Chat + Triage UI                │            │
│  │  (SSE streaming, voice, offline)        │            │
│  └─────────────────────────────────────────┘            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │IndexedDB │  │ServiceWkr│  │WebSpeech │  ← Offline   │
│  └──────────┘  └──────────┘  └──────────┘              │
└──────────────────────────┬───────────────────────────────┘
                           │ /api proxy (SSE)
┌──────────────────────────▼───────────────────────────────┐
│                    FastAPI Backend                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │InputGuard│→ │Supervisor│→ │Retriever │              │
│  └──────────┘  └──────────┘  └──────────┘              │
│       │              │              │                    │
│       │        mode routing    Qdrant hybrid             │
│       │        (keyword)    (dense+BM25+rerank)          │
│       │              │              │                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │Guardrails│← │   LLM    │← │Grounding │              │
│  │(output)  │  │(Claude/  │  │(faithful)│              │
│  └──────────┘  │ Qwen3-8B)│  └──────────┘              │
│                └──────────┘                              │
└──────────────────────────────────────────────────────────┘
```

## Key Decisions

### 1. Dual LLM Backend (Claude API + Local Qwen3-8B)
- **Claude API**: Primary. Prompt caching reduces cost ~90%. Extended thinking
  for complex health queries. Best multilingual quality.
- **Qwen3-8B**: Offline fallback. Runs on local GPU or CPU. Apache 2.0 license.
  Ensures the system works even without internet.

### 2. Offline-First PWA
- **Service Worker**: Cache-first for app shell, network-first for API with
  IndexedDB fallback.
- **IndexedDB**: Stores conversations, cached RAG responses, health facility
  data, and medication reminders.
- **Background Sync**: Queued messages sent when connectivity returns.

### 3. Three-Mode Design
- **VHT Triage**: Follows iCCM protocol (Assess → Classify → Treat/Refer).
  Hard-coded red-flag detection runs BEFORE LLM to ensure danger signs are
  never missed.
- **Maternal Care**: Pregnancy week tracker, ANC milestone reminders, danger
  sign checklist from MoH Essential Maternal Guidelines.
- **Community Health**: General symptom guidance, medication reminders, clinic
  finder.

### 4. Never-Diagnose Guardrails
- System prompts explicitly prohibit diagnosis and prescription.
- Confidence scoring on every response (HIGH/MEDIUM/LOW).
- Abstention when retrieval confidence is too low.
- Mandatory disclaimer on every response.
- Emergency escalation path always visible.

### 5. Multilingual Code-Switching
- bge-m3 embeddings handle multilingual retrieval natively.
- System prompt instructs: "Respond in the user's language. Use English
  medical terms with local-language explanation."
- Supports: English, Luganda, Runyankole, Swahili.

### 6. Knowledge Base
- Sourced from official Uganda MoH publications:
  - VHT Strategy & Operational Guidelines
  - iCCM Protocol
  - Essential Maternal and Newborn Clinical Care Guidelines (2022/2025)
  - Uganda Clinical Guidelines
  - UNEPI Immunization Schedule
- Structured as JSON with metadata: mode, severity, topic, guideline, section.

## File Structure

```
backend/app/
  main.py       — FastAPI app with security middleware, rate limiting, SSE
  service.py    — HealthService orchestrator (pipeline)
  llm.py        — Dual LLM backend (Claude + Qwen3-8B)
  retriever.py  — Qdrant hybrid search + keyword fallback
  guardrails.py — Input/output safety (OWASP LLM Top 10)
  models.py     — Pydantic schemas (ChatRequest/Response, Triage, etc.)
  agents/
    supervisor.py — Mode classifier (keyword-based, no LLM call)
    state.py      — RouteDecision dataclass

frontend/src/
  app/page.tsx      — Main chat interface with SSE streaming
  app/layout.tsx    — Root layout with PWA metadata
  app/globals.css   — Earth-tone glassmorphism design system
  components/       — ChatMessage, ChatInput, ModeSelector, MaternalTracker, etc.
  store/            — Zustand chat state with localStorage persistence
  hooks/            — TanStack Query hooks for API calls
  lib/              — IndexedDB offline storage, service worker registration
```

## Conventions

- Commit messages: conventional commits (feat/fix/docs)
- No Co-Authored-By trailers
- Python: Ruff formatting, type hints throughout
- TypeScript: strict mode, no `any` (except API boundaries)
- CSS: design tokens in :root, no Tailwind (custom glassmorphism system)
