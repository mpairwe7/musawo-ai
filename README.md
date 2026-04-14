---
title: Musawo AI
emoji: 🏥
colorFrom: green
colorTo: yellow
sdk: docker
pinned: true
license: mit
app_port: 7860
---

# Musawo AI — Community Health Navigator `v2.1`

> *"Because every village health worker deserves a smart assistant."*

**Musawo AI** is an offline-first, multilingual health guidance assistant
for rural Uganda. It supports Village Health Teams (VHTs), pregnant
mothers, and community members with evidence-based health guidance
grounded in official Uganda Ministry of Health guidelines.

**Category**: Biology & Physical Health | **Built with**: Groq (Qwen3-32B) + Next.js 16 + FastAPI + Qdrant RAG

[![Deployed on HuggingFace Spaces](https://img.shields.io/badge/HuggingFace-Spaces-blue)](https://huggingface.co/spaces)
[![Tests](https://img.shields.io/badge/tests-112%20passing-brightgreen)]()
[![Knowledge Base](https://img.shields.io/badge/clinical%20entries-92-orange)]()

---

## The Problem

- **68,000+ VHTs** in Uganda are the frontline of community health — but
  still rely on laminated job aids from 2015.
- **16 mothers die every day** in Uganda from preventable causes.
- **70% of Ugandans** live in rural areas with limited internet.

## The Solution

| Mode | For | Key Features |
|------|-----|-------------|
| **VHT Triage** | Village Health Teams | Agentic iCCM assessment (Assess→Classify→Treat/Refer), red-flag voice alerts, treatment protocols with exact dosages |
| **Maternal Care** | Pregnant & new mothers | Pregnancy week tracker, ANC milestones, danger sign alerts, breastfeeding & newborn care |
| **Community Health** | General public | Symptom guidance, medication reminders, GPS clinic finder with embedded map, preventive health |

### What Makes This Different

- **Agentic Triage** — Multi-step iCCM protocol as a stateful AI agent (not single-shot RAG)
- **Deep Conversation Context** — 10-turn history window; follow-up questions remember the full clinical discussion
- **Groq-Powered LLM** — Qwen3-32B via Groq free tier (~500 tok/s), with Claude API and passage-based fallbacks
- **Voice Output** — TTS speaks danger signs aloud in Luganda for VHTs at night
- **92 clinical entries** from the actual Uganda Clinical Guidelines 2016 (exact drug dosages)
- **Grok-Inspired Chat UX** — Markdown rendering, collapsible messages, role avatars, timestamps, section headers
- **Offline-first PWA** with IndexedDB cache + background sync
- **Embedded OSM map** with real GPS distance to 25+ health facilities
- **Twilio SMS** gateway for feature phones (68% of VHTs)
- **Prometheus metrics** for production observability
- **112 automated tests** (87 pytest + 25 vitest)

---

## Quick Start

```bash
# Clone and configure
cd Musawo
cp .env.example .env
# Add your GROQ_API_KEY (free at console.groq.com)
# Optionally add ANTHROPIC_API_KEY, TWILIO creds

# Option 1: Docker (full stack)
docker compose up -d
./scripts/demo-seed.sh
open http://localhost:3000

# Option 2: Local dev (faster iteration)
# Terminal 1 — Backend
cd backend
pip install -r requirements.txt
GROQ_API_KEY=gsk_... QDRANT_URL=http://localhost:6333 uvicorn app.main:app --port 8888

# Terminal 2 — Frontend
cd frontend
npm install
INTERNAL_API_URL=http://localhost:8888 npx next dev --port 3200
# Open http://localhost:3200
```

### LLM Backend Priority Chain

The system tries LLM backends in order and never fails:

1. **Groq API** (free, fast) → Qwen3-32B or Llama-3.3-70B at ~500 tok/s
2. **Claude API** (if key provided) → Sonnet 4.6 with prompt caching
3. **Passage-based** (zero-cost, instant) → Assembles retrieved passages directly

No API key? The app still works — passage-based mode serves clinical content directly from the knowledge base with source citations.

---

## Architecture

```
User (voice/text/SMS) → Next.js 16 PWA (Grok-inspired UI) / Twilio webhook
         ↓                    ↕ IndexedDB + Service Worker
    FastAPI API (port 8888)
         ↓
  InputGuard (OWASP LLM Top 10)
         ↓
  Mode Supervisor → Agentic Triage (VHT) / Standard RAG
         ↓
  Dense Retrieval (Qdrant bge-m3 1024-dim) + cross-mode fallback
         ↓
  LLM (Groq → Claude → Passage-based) + 10-turn conversation history
         ↓
  OutputGuard (PII redaction, grounding, disclaimer) → Voice Output (TTS)
         ↓
  Response (## Assessment → ## Guidance → ## When to Refer → Sources)
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16.2.3, React 19.2, TypeScript, Zustand 5, TanStack Query 5 |
| Backend | FastAPI, Qdrant v1.17, Redis 7.4 |
| LLM | **Groq** (Qwen3-32B / Llama-3.3-70B, free) → Claude Sonnet 4.6 → Passage-based |
| Embeddings | BAAI/bge-m3 (1024-dim, multilingual, CPU) |
| SMS | Twilio (send/receive/webhook) |
| Offline | Service Worker + IndexedDB + Background Sync |
| Maps | OpenStreetMap embeds + Geolocation API + Haversine distance |
| Monitoring | Prometheus + Grafana |
| Security | OWASP LLM Top 10, PII redaction, rate limiting |

### Chat UX (Grok-Inspired)

| Feature | Implementation |
|---------|---------------|
| Markdown rendering | `## Headers`, **bold**, bullet/ordered lists, inline `code`, `---` separators |
| Structured responses | ## Assessment → ## Guidance → ## When to Refer → Sources |
| Message collapsing | Long responses get ▲ Collapse / ▼ Expand button |
| Role avatars | Green "M" circle (Musawo) / Gray "Y" circle (You) |
| Timestamps | HH:MM on every assistant message |
| Clear chat | Trash icon in header, one-tap with confirmation |
| Feedback | Thumbs up/down with voted state animation |
| Confidence badges | HIGH (green) / MED (gold) / LOW (red) pill badges |
| Citations | Expandable sources with guideline name + section |
| Empty state | Gradient welcome screen with quick-start prompts |
| Typing indicator | "Searching health guidelines..." with animated dots |
| Offline banner | Prominent warning with emergency number before user types |

---

## Knowledge Base (92 entries from official sources)

| Source | Entries | Topics |
|--------|---------|--------|
| Uganda Clinical Guidelines 2016 | 45 | Emergencies, malaria, pneumonia, dehydration, NCDs, STIs, cholera, typhoid |
| Essential Maternal Guidelines 2022 | 17 | ANC, pre-eclampsia, PPH, eclampsia, newborn care |
| MIYCAN Nutrition 2021 | 6 | Breastfeeding, FATVAH, micronutrients, local foods |
| iCCM Protocol | 8 | VHT triage, danger signs, malaria/pneumonia/diarrhoea treatment |
| WHO/mhGAP | 4 | Depression, suicide risk, postpartum depression, substance abuse |
| Other (neonatal, child dev) | 12 | Jaundice, sepsis, KMC, developmental milestones, febrile convulsions |

---

## Conversation Context

Musawo maintains **10-turn conversation history** per session, enabling deep multi-turn clinical discussions:

```
Turn 1: "A 2-year-old has fever, RDT positive. ACT dosage?"
  → Correctly gives 2 tablets twice daily for 3 days (12-59 months)

Turn 2: "The same child also has fast breathing at 55/min"
  → Remembers the child, classifies pneumonia (≥40/min threshold)

Turn 3: "Should I refer or treat at home?"
  → Synthesizes BOTH malaria + pneumonia: "Treat both at home with ACT + Amoxicillin"
```

Sessions persist via `session_id` across requests. Frontend stores in `sessionStorage`.

---

## Project Structure

```
Musawo/
├── README.md                    ← This file (v2.1)
├── README.v1.0.md               ← Original v1.0
├── ETHICS.md                    ← Deep ethical analysis + NDPA compliance
├── CLAUDE.md                    ← Architecture decisions
├── DEMO.md                      ← 3-minute demo script
├── docker-compose.yml
├── Dockerfile                   ← HuggingFace Spaces deploy
├── render.yaml                  ← Render.com deploy
├── backend/
│   ├── app/
│   │   ├── main.py              ← API + Twilio webhook + metrics + facilities
│   │   ├── service.py           ← RAG orchestrator + session management
│   │   ├── llm.py               ← Groq + Claude + Passage-based (3-tier fallback)
│   │   ├── retriever.py         ← Qdrant dense search (bge-m3 CPU)
│   │   ├── guardrails.py        ← OWASP LLM Top 10
│   │   ├── sms_gateway.py       ← Twilio SMS + USSD menu tree
│   │   ├── metrics.py           ← Prometheus counters/histograms
│   │   ├── models.py            ← Pydantic schemas
│   │   └── agents/
│   │       ├── triage_agent.py  ← Agentic iCCM workflow (multi-step)
│   │       ├── supervisor.py    ← Mode classifier + red-flag detection
│   │       └── state.py         ← Routing state
│   ├── tests/                   ← 87 pytest cases (5 test files)
│   └── requirements.txt         ← openai, anthropic, twilio, prometheus, etc.
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx         ← Grok-inspired chat + agentic toggle + panels
│   │   │   ├── layout.tsx       ← PWA metadata + dynamic lang
│   │   │   └── globals.css      ← Earth-tone glassmorphism design system
│   │   ├── components/          ← 12 React components
│   │   │   ├── ChatMessage.tsx  ← Markdown renderer + collapse + avatars
│   │   │   ├── ChatInput.tsx    ← Voice input + forwarded ref
│   │   │   ├── ClinicFinder.tsx ← GPS + OSM map + distance sorting
│   │   │   ├── MaternalTracker  ← Pregnancy week + ANC milestones
│   │   │   ├── MedicationReminders ← IndexedDB CRUD
│   │   │   ├── SettingsPanel    ← Cache management
│   │   │   └── InstallPrompt   ← PWA install banner
│   │   ├── lib/
│   │   │   ├── voiceOutput.ts   ← TTS for danger signs (4 languages)
│   │   │   ├── offlineDb.ts     ← IndexedDB (conversations, cache, queue)
│   │   │   └── serviceWorkerRegistration.ts
│   │   ├── store/useChatStore.ts ← Zustand + localStorage persistence
│   │   ├── hooks/useApi.ts      ← TanStack Query + useAgenticTriage
│   │   └── __tests__/           ← 25 vitest cases (SSE parser, store)
│   ├── public/
│   │   ├── sw.js                ← Service worker + real background sync
│   │   └── manifest.json        ← PWA manifest with shortcuts
│   └── next.config.mjs          ← CSP (dev/prod), API proxy, headers
├── knowledge-base/              ← 15 JSON files, 92 clinical entries
│   ├── ucg-emergencies/         ← Shock, dehydration, burns, snakebite, poisoning
│   ├── ucg-infectious-diseases/ ← Malaria, STIs, HIV ART, cholera, typhoid, measles
│   ├── ucg-chronic-diseases/    ← Hypertension, diabetes, depression, epilepsy, TB
│   ├── ucg-maternal-obstetric/  ← Pre-eclampsia, eclampsia, PPH, MgSO4 protocol
│   ├── ucg-childhood-illness/   ← Developmental milestones, iCCM, febrile convulsions
│   ├── maternal-guidelines/     ← ANC, newborn care, breastfeeding, immunization
│   ├── nutrition-miycan/        ← FATVAH, micronutrients, local food groups
│   ├── mental-health/           ← Depression, suicide risk, substance abuse
│   ├── neonatal-care/           ← Jaundice, sepsis, KMC, breathing problems
│   ├── emergency-protocols/     ← PPH, eclampsia, choking, anaphylaxis
│   ├── health-facilities/       ← 25 facilities with GPS coords
│   ├── vht-guidelines/          ← iCCM protocols
│   └── symptom-protocols/       ← Community health guidance
├── monitoring/                  ← Prometheus + Grafana config
└── scripts/
    ├── reindex.sh               ← KB indexing into Qdrant
    └── demo-seed.sh             ← Demo preparation + smoke tests
```

---

## Emergency Contacts (Uganda)

| Service | Number |
|---------|--------|
| MoH Health Hotline | **0800 100 263** (toll-free, 24/7) |
| National Ambulance | **0800 911 911** |
| Poison Centre | +256-414-270-975 |

---

## License

MIT. Knowledge base content derived from publicly available Uganda MoH publications.

## Acknowledgments

- Uganda Ministry of Health — Clinical Guidelines 2016, Maternal Guidelines 2022
- UNICEF — MIYCAN Nutrition Guidelines 2021
- WHO — iCCM Protocol, mhGAP Guidelines
- Groq — Free LLM inference (Qwen3-32B, Llama-3.3-70B)
- Anthropic — Claude API
- Twilio — SMS delivery
