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

# Musawo AI — Community Health Navigator `v2.0`

> *"Because every village health worker deserves a smart assistant."*

**Musawo AI** is an offline-first, multilingual health guidance assistant
for rural Uganda. It supports Village Health Teams (VHTs), pregnant
mothers, and community members with evidence-based health guidance
grounded in official Uganda Ministry of Health guidelines.

**Category**: Biology & Physical Health | **Built with**: Claude API + Next.js 16 + FastAPI + Qdrant Hybrid RAG

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
| **Community Health** | General public | Symptom guidance, medication reminders, GPS clinic finder with map, preventive health |

### What Makes This Different

- **Agentic Triage** — Multi-step iCCM protocol as a stateful AI agent (not single-shot RAG)
- **Voice Output** — TTS speaks danger signs aloud in Luganda for VHTs at night
- **92 clinical entries** from the actual Uganda Clinical Guidelines 2016 (exact drug dosages)
- **Offline-first PWA** with IndexedDB cache + background sync
- **Embedded OSM map** with real GPS distance to 25 health facilities
- **Twilio SMS** gateway for feature phones (68% of VHTs)
- **Prometheus metrics** for production observability
- **112 automated tests** (87 pytest + 25 vitest)

---

## Quick Start

```bash
# Clone and configure
cd Musawo
cp .env.example .env           # Add ANTHROPIC_API_KEY + TWILIO creds

# Start all services
docker compose up -d

# Index knowledge base + verify
./scripts/demo-seed.sh

# Open
open http://localhost:3000
```

### Hugging Face Spaces Deployment

This repo is configured for HuggingFace Spaces with Docker SDK.
Push to a HF Space and it auto-deploys.

---

## Architecture

```
User (voice/text/SMS) → Next.js 16 PWA / Twilio webhook
         ↓                    ↕ IndexedDB + Service Worker
    FastAPI API
         ↓
  InputGuard (OWASP LLM Top 10)
         ↓
  Mode Supervisor → Agentic Triage (VHT) / Standard RAG
         ↓
  Hybrid Retrieval (Qdrant dense + BM25 + cross-encoder)
         ↓
  LLM (Claude API / Qwen3-8B offline) → Voice Output (TTS)
         ↓
  OutputGuard (PII redaction, grounding, disclaimer)
         ↓
  Response + Triage Card + Citations + Confidence
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16.2.3, React 19.2, TypeScript, Zustand 5, TanStack Query 5 |
| Backend | FastAPI, Qdrant v1.17, Redis 7.4 |
| LLM | Claude Sonnet 4.6 (prompt-cached) / Qwen3-8B (offline) |
| Embeddings | BAAI/bge-m3 (1024-dim, multilingual) |
| SMS | Twilio (send/receive/webhook) |
| Offline | Service Worker + IndexedDB + Background Sync |
| Maps | OpenStreetMap embeds + Geolocation API |
| Monitoring | Prometheus + Grafana |
| Security | OWASP LLM Top 10, PII redaction, rate limiting |

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

## Project Structure

```
Musawo/
├── README.md                    ← This file (v2.0)
├── README.v1.0.md               ← Original v1.0
├── ETHICS.md                    ← Deep ethical analysis
├── CLAUDE.md                    ← Architecture decisions
├── DEMO.md                      ← 3-minute demo script
├── docker-compose.yml
├── Dockerfile                   ← HuggingFace Spaces deploy
├── render.yaml                  ← Render.com deploy
├── backend/
│   ├── app/
│   │   ├── main.py              ← API + Twilio webhook + metrics
│   │   ├── service.py           ← RAG orchestrator
│   │   ├── llm.py               ← Claude + Qwen3-8B dual backend
│   │   ├── retriever.py         ← Hybrid search
│   │   ├── guardrails.py        ← OWASP LLM Top 10
│   │   ├── sms_gateway.py       ← Twilio SMS + USSD menu
│   │   ├── metrics.py           ← Prometheus counters/histograms
│   │   └── agents/
│   │       ├── triage_agent.py  ← Agentic iCCM workflow
│   │       └── supervisor.py    ← Mode classifier
│   └── tests/                   ← 87 pytest cases
├── frontend/
│   ├── src/
│   │   ├── app/page.tsx         ← Main chat + triage + agentic toggle
│   │   ├── components/          ← 12 React components
│   │   ├── lib/voiceOutput.ts   ← TTS for danger signs
│   │   └── __tests__/           ← 25 vitest cases
│   └── public/sw.js             ← Service worker + background sync
├── knowledge-base/              ← 15 JSON files, 92 entries
├── monitoring/                  ← Prometheus + Grafana config
└── scripts/
    ├── reindex.sh               ← KB indexing
    └── demo-seed.sh             ← Demo preparation
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
- Anthropic — Claude API
- Twilio — SMS delivery
