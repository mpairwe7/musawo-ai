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

# Musawo AI — Community Health Navigator `v2.5`

> *"Because every village health worker deserves a smart assistant."*

**Musawo AI** is an offline-first, multilingual health guidance assistant
for rural Uganda. It supports Village Health Teams (VHTs), pregnant
mothers, and community members with evidence-based health guidance
grounded in official Uganda Ministry of Health guidelines.

**Category**: Biology & Physical Health | **Built with**: Groq + Sunbird AI + Next.js 16 + FastAPI + Qdrant RAG

[![Deployed on HuggingFace Spaces](https://img.shields.io/badge/HuggingFace-Spaces-blue)](https://huggingface.co/spaces)
[![Tests](https://img.shields.io/badge/tests-217%20passing-brightgreen)]()
[![Knowledge Base](https://img.shields.io/badge/clinical%20entries-203-orange)]()
[![PWA](https://img.shields.io/badge/PWA-installable-purple)]()
[![Locales](https://img.shields.io/badge/languages-4%20(EN%2FLG%2FNYN%2FSW)-blue)]()
[![Grade](https://img.shields.io/badge/eval%20grade-A%20(91%25)-brightgreen)]()

---

## The Problem

- **68,000+ VHTs** in Uganda are the frontline of community health — but
  still rely on laminated job aids from 2015.
- **16 mothers die every day** in Uganda from preventable causes.
- **70% of Ugandans** live in rural areas with limited internet.

## The Solution

| Mode | For | Key Features |
|------|-----|-------------|
| **VHT Triage** | Village Health Teams | Agentic iCCM assessment (Assess->Classify->Treat/Refer), red-flag voice alerts, treatment protocols with exact dosages |
| **Maternal Care** | Pregnant & new mothers | Pregnancy week tracker, ANC milestones, danger sign alerts, breastfeeding & newborn care |
| **Community Health** | General public | Symptom guidance, medication reminders, GPS clinic finder with embedded map, preventive health |

### What Makes This Different

- **Agentic Triage** — Multi-step iCCM protocol as a stateful AI agent classifying 6 conditions (malaria, pneumonia, diarrhoea, measles, SAM, MAM) with negation-aware danger sign detection, dehydration grading, and MUAC integration
- **Sunbird AI Integration** — Native Ugandan language STT/TTS/translation for Luganda, Runyankole, Swahili via [Sunbird AI](https://docs.sunbird.ai) with auto-refreshing auth tokens
- **6-Tier LLM Fallback** — Groq API → Claude API → GGUF/llama.cpp → BitsAndBytes 4-bit → Full-precision → Passage-based. Never fails silently.
- **Deep Conversation Context** — 10-turn history window with token budget enforcement preventing context overflow
- **Optimized Retrieval** — Query expansion (19 health synonym clusters) + stop word removal + section name boosting + severity weighting + LRU cache + dual-search for multilingual queries
- **Clinical Safety** — Audit trail (JSONL), clinical safety gate (faithfulness < 0.2 blocked), negation-aware red-flags in 4 languages, hybrid faithfulness scoring
- **Full i18n** — 50+ backend keys + 30+ frontend keys in EN/LG/NYN/SW. Locale-aware LLM prompts, guardrail messages, disclaimers, triage responses, USSD menus
- **Voice Fallback Chain** — STT: Sunbird → Parakeet TDT 0.6B → Moonshine 27M → faster-whisper. TTS: Sunbird native speakers → CosyVoice2 → edge-tts → browser
- **Inline Health Diagrams** — 10 SVG clinical illustrations auto-detected or invoked via `::diagram[key]`
- **Grok-Inspired Chat UX** — Semantic section headers, collapsible messages, compact pills, responsive composer
- **Offline-first PWA** with IndexedDB cache + background sync + installable on any device
- **Production Security** — CORS hardened, SMS auth + rate limiting, Twilio webhook signature validation, audio size limits, phone number validation, prompt injection defense
- **Embedded OSM map** with real GPS distance to 25+ health facilities
- **Smart Facility Routing** — Location queries ("nearest clinic") answered directly with Clinic Finder instructions instead of irrelevant RAG results
- **Twilio SMS/USSD** gateway with i18n menus and language selection
- **Prometheus metrics** — locale-aware confidence, abstention, escalation tracking
- **217 automated tests** (45 bench_eval + 149 pytest + 23 vitest) — **Grade A (91%)**

---

## Quick Start

```bash
# Clone and configure
cd Musawo
cp .env.example .env
# Add your GROQ_API_KEY (free at console.groq.com)
# Add SUNBIRD_USERNAME + SUNBIRD_PASSWORD (free at sunbird.ai)
# Optionally add ANTHROPIC_API_KEY, TWILIO creds

# Option 1: Docker (full stack, production-ready)
docker compose up -d
./scripts/demo-seed.sh
open http://localhost:3000

# Option 2: Local dev (faster iteration)
# Terminal 1 — Backend
cd backend
pip install -r requirements.txt
GROQ_API_KEY=gsk_... \
SUNBIRD_USERNAME=your_user SUNBIRD_PASSWORD=your_pass \
QDRANT_URL=http://localhost:6333 \
uvicorn app.main:app --port 8888

# Terminal 2 — Frontend
cd frontend
npm install
INTERNAL_API_URL=http://localhost:8888 npx next dev --port 3200
# Open http://localhost:3200

# Run production evaluation
cd backend && python -m tests.bench_eval
```

### LLM Backend Priority Chain

The system tries 6 backends in order and never fails:

1. **Groq API** (free, fast) -> Llama-3.3-70B or Qwen3-32B at ~500 tok/s
2. **Claude API** (if key provided) -> Sonnet 4.6 with prompt caching + extended thinking
3. **GGUF via llama.cpp** (offline) -> Qwen3-8B Q5_K_M, ~5GB RAM on CPU
4. **4-bit BitsAndBytes** (GPU) -> Auto-detected, ~4GB VRAM
5. **Full-precision transformers** -> Qwen3-8B float16/float32
6. **Passage-based** (zero-cost, instant) -> Locale-aware templates in 4 languages

No API key? The app still works — passage-based mode serves clinical content directly from the knowledge base with source citations in the user's language.

### Voice & Translation Backend Chain

| Layer | Cloud Primary | Local Primary | Local Fallback |
|-------|--------------|---------------|----------------|
| **STT** | Sunbird API (Luganda/Runyankole/Swahili) | Parakeet TDT 0.6B | Moonshine 27M / faster-whisper |
| **TTS** | Sunbird native speakers | CosyVoice2-0.5B | edge-tts |
| **Translation** | Sunbird neural (EN↔LG/NYN) | 200+ health term keyword map | — |
| **Language detect** | Sunbird ML detection | Keyword heuristic (38 LG + 20 NYN + 28 SW terms) | — |

---

## Architecture (v2.5)

```
User (voice/text/SMS) -> Next.js 16 PWA (Grok-inspired UI) / Twilio webhook
         |                    | IndexedDB + Service Worker + Background Sync
         |                    | Sunbird STT → Parakeet → Moonshine → Browser
    FastAPI API (port 8888)
         |
  InputGuard (OWASP LLM Top 10, i18n, negation-aware)
         |
  Facility Query Detector → Direct response (skips RAG for location queries)
         |
  Mode Supervisor (multilingual keywords + negation-aware red-flags)
         |                    → Agentic Triage (6 conditions, MUAC, dehydration)
         |                    → Standard RAG
  Sunbird Translation → Query Expansion → Dense Retrieval (Qdrant bge-m3)
         |                    + Section boosting + Severity weighting + LRU cache
         |                    + Dual-search (EN translation + original) + Cross-mode fallback
  LLM (Groq → Claude → GGUF → BnB4 → FP16 → Passages) + token budget
         |
  Clinical Safety Gate (faithfulness < 0.2 → block/warn)
         |
  OutputGuard (PII, grounding, i18n disclaimer) → Audit Trail (JSONL)
         |
  Response (## Guidance → ## When to Refer → Sources) + Diagrams
         |
  Sunbird TTS → CosyVoice → edge-tts → Browser → Chat UI / SMS / USSD
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16.2.3, React 19.2, TypeScript 5.8, Zustand 5, TanStack Query 5 |
| Backend | FastAPI, Qdrant v1.17, Redis 7.4 |
| LLM | **Groq** → Claude → GGUF/llama.cpp → BitsAndBytes 4-bit → Passage-based |
| Voice | **Sunbird AI** (STT/TTS/translate) → Parakeet TDT 0.6B → CosyVoice2 → edge-tts |
| Embeddings | BAAI/bge-m3 (1024-dim, multilingual, CPU) |
| SMS | Twilio (send/receive/webhook, i18n USSD menu tree) |
| i18n | Backend: 50+ keys, Frontend: 30+ keys (EN/LG/NYN/SW) |
| Offline | Service Worker + IndexedDB (5 stores) + Background Sync |
| Maps | OpenStreetMap embeds + Geolocation API + Haversine distance |
| Diagrams | 10 inline SVG health illustrations (fully offline) |
| Safety | Clinical safety gate, audit trail (JSONL), negation-aware red-flags |
| Monitoring | Prometheus (locale-aware confidence, abstention, escalation metrics) |
| Security | OWASP LLM Top 10, PII redaction, SMS auth, Twilio sig validation |
| Testing | bench_eval (45) + pytest (149) + vitest (23) = **217 tests, Grade A (91%)** |

### Chat UX (Grok-Inspired, 2026 Standards)

| Feature | Implementation |
|---------|---------------|
| Semantic section headers | Color-coded by type: Assessment (blue), Guidance (green), When to Refer (red), Follow-up (gold), Sources (gray) |
| Structured responses | ## Assessment -> ## Guidance -> ## When to Refer -> Sources |
| REFER NOW badge | Inline red pulsing badge for urgent referrals |
| Inline health diagrams | Auto-detected from content keywords or `::diagram[key]` syntax |
| Markdown rendering | `## Headers`, **bold**, bullet/ordered lists, inline `code`, `---` separators |
| Message collapsing | Long responses get Collapse/Expand button |
| Role avatars | Green "M" circle (Musawo) / Gray "Y" circle (You) |
| Timestamps | HH:MM on every assistant message |
| Multi-session sidebar | Session history, switching, auto-titling, delete |
| Feedback | Thumbs up/down with voted state animation |
| Confidence badges | HIGH (green) / MED (gold) / LOW (red) pill badges |
| Citations | Expandable sources with guideline name + section |
| Phone auto-linking | 0800 and +256 numbers become tappable tel: links |
| Empty state | Gradient welcome screen with locale-aware quick-start prompts |
| Typing indicator | "Searching health guidelines..." with animated dots |
| Offline banner | Prominent warning with emergency number |
| SW update toast | "A new version is available" with Update button |
| Skeleton loading | Full app skeleton (header, mode cards, empty state) on first load |

### Inline Health Diagrams

Musawo auto-detects clinical topics and shows relevant SVG illustrations:

| Diagram Key | Content | Trigger Keywords |
|------------|---------|-----------------|
| `danger_signs` | 6 child danger sign icons | "danger sign", "convulsion", "unable to drink" |
| `ors_preparation` | 4-step ORS mixing visual | "ORS", "oral rehydration", "rehydration salt" |
| `handwashing` | 5-step handwashing guide | "handwashing", "wash hands", "hand hygiene" |
| `breathing_count` | Clock + thresholds | "breathing rate", "count breath", "fast breathing" |
| `breastfeeding` | Position checklist + warnings | "breastfeed", "latch", "breast position" |
| `immunization_schedule` | UNEPI timeline (birth-9mo) | "immuniz", "vaccin", "BCG", "pentavalent" |
| `dehydration_check` | 3-column assessment | "dehydrat", "skin pinch", "sunken eyes" |
| `birth_preparedness` | 4 preparation pillars | "birth plan", "birth prepar", "delivery plan" |
| `malaria_rdt` | 4-step RDT process + result reading | "RDT", "rapid diagnostic", "malaria test" |
| `fever_assessment` | 3-tier temperature thresholds + actions | "high fever", "fever child", "temperature 38" |

All diagrams are inline SVGs — **zero network requests, fully offline**.

---

## Knowledge Base (203 entries from official sources)

| Source | Files | Entries | Topics |
|--------|-------|---------|--------|
| Uganda Clinical Guidelines 2016 | 6 | 43 | Emergencies, malaria, pneumonia, dehydration, NCDs, STIs, cholera, typhoid |
| Essential Maternal Guidelines 2022 | 2 | 17 | ANC, pre-eclampsia, PPH, eclampsia, newborn care, postpartum FP, KMC |
| UNEPI Immunization Schedule | 1 | 20 | Birth-9mo vaccines, TT for pregnant women, HPV, catch-up, cold chain |
| Family Planning Guidelines | 1 | 29 | COCs, POPs, DMPA, implants, IUDs, condoms, LAM, emergency, myths |
| HIV/TB Guidelines (Treat All) | 1 | 14 | ART/TLD, viral load, PMTCT, TB-RHZE, co-infection, PrEP/PEP |
| WASH/Prevention | 1 | 12 | Water treatment, handwashing, latrines, malaria ITNs, cholera prevention |
| First Aid/Emergencies | 1 | 15 | Burns, snakebite, drowning, choking, bleeding, fractures, dog bites |
| iCCM Protocol | 1 | 8 | VHT triage, danger signs, malaria/pneumonia/diarrhoea treatment |
| MIYCAN Nutrition 2021 | 1 | 9 | Breastfeeding, FATVAH, complementary feeding, iron deficiency |
| Symptom Protocols | 1 | 12 | Skin rashes, eye infections, ear pain, urinary symptoms |
| Mental Health | 1 | 7 | Depression, anxiety, substance abuse, GBV psychosocial support |
| Neonatal Care | 1 | 7 | Jaundice, sepsis, KMC, cord care, hypothermia, feeding difficulty |
| Obstetric Emergencies | 1 | 7 | Eclampsia, PPH, cord prolapse, retained placenta, shoulder dystocia |
| Childhood Illness | 1 | 8 | Development, MUAC screening, deworming, Vitamin A supplementation |

**20 knowledge base files** across 18 clinical domains. All sourced from:
- Uganda Ministry of Health official publications
- WHO clinical guidelines and protocols
- UNICEF MIYCAN nutrition framework

---

## Conversation Context

Musawo maintains **10-turn conversation history** per session, enabling deep multi-turn clinical discussions:

```
Turn 1: "A 2-year-old has fever, RDT positive. ACT dosage?"
  -> Correctly gives 2 tablets twice daily for 3 days (12-59 months)

Turn 2: "The same child also has fast breathing at 55/min"
  -> Remembers the child, classifies pneumonia (>=40/min threshold)

Turn 3: "Should I refer or treat at home?"
  -> Synthesizes BOTH malaria + pneumonia: "Treat both at home with ACT + Amoxicillin"
```

Sessions persist via `session_id` across requests. Multi-session sidebar allows switching between conversations.

---

## PWA Features

Musawo is a fully installable Progressive Web App:

| Feature | Implementation |
|---------|---------------|
| Installable | Web manifest with 5 icon sizes (72-512px), app shortcuts |
| Offline cache | Service Worker: cache-first app shell, network-first API |
| Background sync | Queued messages sent when connectivity returns |
| IndexedDB stores | conversations, cachedResponses, offlineQueue, facilities, medicationReminders |
| Push notifications | Service Worker push handler for medication reminders |
| SW update prompt | Toast notification when new version available |
| Skeleton loading | Full app skeleton on first load |
| Safe area insets | Proper padding for notched/rounded screens |
| Touch targets | 44px minimum (WCAG 2.5.8) |
| Reduced motion | Respects prefers-reduced-motion |

---

## Project Structure

```
Musawo/
├── README.md                    <- This file (v2.5)
├── README.v1.0.md               <- Original v1.0
├── ETHICS.md                    <- Deep ethical analysis + NDPA compliance
├── CLAUDE.md                    <- Architecture decisions
├── DEMO.md                      <- 3-minute demo script
├── docker-compose.yml
├── Dockerfile                   <- HuggingFace Spaces deploy
├── render.yaml                  <- Render.com deploy
├── .env.example                 <- Full configuration template
├── backend/
│   ├── app/
│   │   ├── main.py              <- 19 API endpoints + middleware + security
│   │   ├── service.py           <- RAG orchestrator + sessions + audit trail
│   │   ├── llm.py               <- 6-tier LLM fallback + token counting
│   │   ├── retriever.py         <- Qdrant dense + query expansion + cache
│   │   ├── guardrails.py        <- Safety gate + negation-aware + i18n
│   │   ├── sunbird.py           <- Sunbird AI: STT/TTS/translate + auto-refresh
│   │   ├── i18n.py              <- Centralized i18n (50+ keys, 4 languages)
│   │   ├── sms_gateway.py       <- Twilio SMS + i18n USSD menu tree
│   │   ├── metrics.py           <- Prometheus (locale-aware metrics)
│   │   ├── models.py            <- Pydantic schemas
│   │   └── agents/
│   │       ├── triage_agent.py  <- Agentic iCCM (6 conditions, MUAC, dehydration)
│   │       ├── supervisor.py    <- Mode classifier + multilingual red-flags
│   │       └── state.py         <- RouteDecision dataclass
│   ├── tests/                   <- 149 pytest + 45 bench_eval
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx         <- Chat UI + sessions + panels + streaming
│   │   │   ├── layout.tsx       <- PWA metadata + OG tags + JSON-LD
│   │   │   ├── globals.css      <- #0F0F0F dark + glassmorphism design system
│   │   │   ├── loading.tsx      <- Skeleton loading screen
│   │   │   └── error.tsx        <- Error boundary with emergency hotline
│   │   ├── components/          <- 15 React components
│   │   │   ├── ChatMessage.tsx  <- Markdown + diagrams + TTS toggle + feedback
│   │   │   ├── ChatInput.tsx    <- Voice modal trigger + auto-resize
│   │   │   ├── VoiceModal.tsx   <- Floating voice input: waveform + transcription
│   │   │   ├── VoicePersonnelModal.tsx <- Voice persona selection + preview
│   │   │   ├── ClinicFinder.tsx <- GPS + OSM map + Haversine distance
│   │   │   ├── HealthDiagrams.tsx <- 10 inline SVG clinical illustrations
│   │   │   ├── MaternalTracker.tsx <- Pregnancy week + localized danger signs (4 langs)
│   │   │   ├── MedicationReminders.tsx <- IndexedDB CRUD
│   │   │   ├── ModeSelector.tsx <- Mode switching cards
│   │   │   ├── StarterPrompts.tsx <- 4-language quick-start prompts
│   │   │   ├── SettingsPanel.tsx <- TTS, font size, contrast, cache, about
│   │   │   ├── InstallPrompt.tsx <- PWA install banner
│   │   │   ├── Icons.tsx        <- 19 SVG icon components
│   │   │   └── Providers.tsx    <- TanStack Query provider
│   │   ├── lib/
│   │   │   ├── voiceOutput.ts   <- TTS: Sunbird → CosyVoice → edge-tts → browser
│   │   │   ├── i18n.ts          <- Frontend i18n (30+ keys, 4 languages)
│   │   │   ├── offlineDb.ts     <- IndexedDB (5 stores, TTL cache)
│   │   │   └── serviceWorkerRegistration.ts <- SW register + update events
│   │   ├── store/useChatStore.ts <- Zustand + sessions + voice persona + persist
│   │   ├── hooks/useApi.ts      <- TanStack Query + useAgenticTriage
│   │   └── __tests__/           <- 23 vitest cases (SSE parser, store)
│   ├── public/
│   │   ├── sw.js                <- Service worker + background sync + push
│   │   ├── manifest.json        <- PWA manifest with shortcuts
│   │   ├── icons/               <- 5 PNG icon sizes + source SVG
│   │   └── favicon-*.png        <- Favicons (16px, 32px)
│   └── next.config.mjs          <- CSP headers, API proxy, standalone output
├── knowledge-base/              <- 20 JSON files, 203 clinical entries
│   ├── vht-guidelines/          <- iCCM protocols (8 entries)
│   ├── maternal-guidelines/     <- ANC, newborn, postpartum FP, KMC (12 entries)
│   ├── ucg-infectious-diseases/ <- Malaria, STIs, HIV, cholera (20 entries)
│   ├── ucg-emergencies/         <- Shock, burns, snakebite (10 entries)
│   ├── ucg-chronic-diseases/    <- NCDs, hypertension, diabetes (8 entries)
│   ├── ucg-childhood-illness/   <- Child development, MUAC, deworming (8 entries)
│   ├── ucg-maternal-obstetric/  <- Pre-eclampsia, PPH (5 entries)
│   ├── immunization/            <- UNEPI schedule, HPV, TT (20 entries)
│   ├── family-planning/         <- All methods, myths, counseling (29 entries)
│   ├── hiv-tb-adherence/        <- ART, viral load, PMTCT, TB (14 entries)
│   ├── wash-prevention/         <- Water, sanitation, malaria nets (12 entries)
│   ├── first-aid/               <- Burns, snakebite, choking, CPR (15 entries)
│   ├── nutrition-miycan/        <- FATVAH, complementary feeding, anemia (9 entries)
│   ├── mental-health/           <- Depression, anxiety, GBV, substance abuse (7 entries)
│   ├── neonatal-care/           <- Jaundice, cord care, hypothermia, KMC (7 entries)
│   ├── emergency-protocols/     <- Obstetric emergencies, cord prolapse (7 entries)
│   ├── health-facilities/       <- 25+ facilities with GPS
│   └── symptom-protocols/       <- Skin, eye, ear, urinary symptoms (12 entries)
├── monitoring/                  <- Prometheus + Grafana config
└── scripts/
    ├── reindex.sh               <- KB indexing into Qdrant
    └── demo-seed.sh             <- Demo preparation + smoke tests
```

---

## API Endpoints (19 total)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/health` | Health check (includes sunbird_ai status) | — |
| GET | `/ready` | Readiness check (LLM + retriever) | — |
| GET | `/metrics` | Prometheus metrics (locale-aware) | — |
| POST | `/v1/chat` | Single-shot RAG chat (dual-search, i18n) | — |
| POST | `/v1/chat/stream` | SSE streaming response | — |
| POST | `/v1/triage` | Agentic iCCM triage (6 conditions, MUAC) | — |
| GET | `/v1/modes` | List health modes with metadata | — |
| GET | `/v1/facilities` | Health facility search | — |
| GET | `/v1/facilities/nearby` | GPS proximity facility lookup | — |
| POST | `/v1/voice/stt` | Speech-to-text (Sunbird → Parakeet) | — |
| POST | `/v1/voice/tts` | Text-to-speech (Sunbird native voices) | — |
| POST | `/v1/translate` | Translate EN↔LG/NYN | — |
| POST | `/v1/detect-language` | Auto-detect language (Sunbird ML) | — |
| POST | `/v1/ussd/callback` | USSD menu tree (i18n, language select) | — |
| POST | `/v1/sms/send` | Send SMS via Twilio | API key |
| POST | `/v1/sms/webhook` | Incoming SMS handler | Twilio sig |
| GET | `/v1/session/{id}/history` | Session resumption | — |
| POST | `/v1/feedback` | User feedback submission | — |
| GET | `/v1/emergency-contacts` | Uganda emergency hotlines | — |

---

## Testing (217 total)

```bash
# Production benchmark suite (45 tests, requires running backend)
cd backend && python -m tests.bench_eval

# Backend unit tests (149 tests)
cd backend && python3 -m pytest tests/ -v

# Frontend unit tests (23 tests)
cd frontend && npx vitest run

# TypeScript check
cd frontend && npx tsc --noEmit
```

### Benchmark Suite (`tests/bench_eval.py`) — Grade A (91%)

| Benchmark | Score | What it tests |
|-----------|-------|---------------|
| Retrieval Quality | 88% | MRR, Recall@4, term coverage on 8 gold-standard queries |
| Multilingual | 75% | LG/NYN/SW confidence vs EN baseline |
| Clinical Safety | 100% | Danger sign detection + negation + escalation accuracy |
| Security | 100% | 5 prompt injection attacks (none leaked) |
| Facility Routing | 100% | EN/LG/SW location queries → no irrelevant content |
| Latency | 100% | P50=1s, P95=10s, cached=1ms |
| Audit Trail | 100% | JSONL completeness (timestamp, session, confidence) |
| **Overall** | **91%** | **Production Ready** |

### Unit Test Suites

| Suite | Tests | Coverage |
|-------|-------|---------|
| test_api.py | 15 | All 19 API endpoints, validation, rate limiting |
| test_guardrails.py | 28 | Prompt injection, PII redaction, abstention, crisis escalation, i18n |
| test_models.py | 11 | Pydantic schemas, validation ranges |
| test_supervisor.py | 17 | Mode classification, multilingual red-flag detection, negation |
| test_triage_agent.py | 16 | Multi-turn triage, 6 conditions, MUAC, comorbidity |
| test_retriever.py | 17 | BM25, circuit breaker, faithfulness, citations, keyword fallback, cache |
| test_llm.py | 15 | Passage formatting, system prompts, 6-tier fallback, token counting |
| test_service.py | 14 | SessionStore, input guard, abstention, audit trail, escalation |
| parseSSE.test.ts | 10 | SSE buffer parsing, CRLF handling, edge cases |
| useChatStore.test.ts | 13 | Zustand store, turn limits, session management |

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

- Uganda Ministry of Health — Clinical Guidelines 2016, Maternal Guidelines 2022, VHT Strategy
- UNICEF — MIYCAN Nutrition Guidelines 2021
- WHO — iCCM Protocol, mhGAP Guidelines, Medical Eligibility Criteria
- [Sunbird AI](https://sunbird.ai) — Native Ugandan language STT/TTS/translation
- Groq — Free LLM inference (Llama-3.3-70B, Qwen3-32B)
- Anthropic — Claude API with prompt caching
- NVIDIA — Parakeet TDT 0.6B ASR model
- FunAudioLLM — CosyVoice2 TTS model
- Twilio — SMS/USSD delivery
- OpenStreetMap — Map tiles and geolocation
