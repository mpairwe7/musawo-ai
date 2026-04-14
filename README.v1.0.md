# Musawo AI — Community Health Navigator

> *"Because every village health worker deserves a smart assistant."*

**Musawo AI** is an offline-first, multilingual health guidance assistant
for rural Uganda. It supports Village Health Teams (VHTs), pregnant
mothers, and community members with evidence-based health guidance
grounded in official Uganda Ministry of Health guidelines.

**Category**: Biology & Physical Health
**Built with**: Claude API + Next.js 16 + FastAPI + Qdrant Hybrid RAG

---

## The Problem

- **68,000+ VHTs** in Uganda are the frontline of community health — but
  still rely on laminated job aids from 2015.
- **16 mothers die every day** in Uganda from preventable causes.
  Many delays happen because danger signs aren't recognized early.
- **70% of Ugandans** live in rural areas with limited internet and
  few health workers.

## The Solution

Musawo AI provides three integrated health modes:

| Mode | For | Features |
|------|-----|----------|
| **VHT Triage** | Village Health Teams | iCCM-based symptom assessment, red-flag detection, treatment protocols, referral guidance |
| **Maternal Care** | Pregnant & new mothers | Pregnancy week tracker, ANC milestones, danger sign alerts, breastfeeding & newborn care |
| **Community Health** | General public | Symptom guidance, medication reminders, nearest clinic finder, preventive health |

### Key Capabilities

- **Offline-first PWA** — works without internet via Service Worker + IndexedDB
- **Multilingual** — Luganda, Runyankole, Swahili, English with natural code-switching
- **Voice-first** — Web Speech API for low-literacy users
- **Never diagnoses** — guidance only, with confidence scoring and mandatory escalation
- **Grounded in MoH guidelines** — every response cites official sources
- **Emergency escalation** — danger signs trigger immediate REFER NOW + hotline

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Anthropic API key (for Claude) — or use local Qwen3-8B (offline mode)

### Run

```bash
# 1. Clone and configure
cd Musawo
cp .env.example .env
# Edit .env → add your ANTHROPIC_API_KEY

# 2. Start all services
docker compose up -d

# 3. Index the health knowledge base
./scripts/reindex.sh

# 4. Open in browser
open http://localhost:3000
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| Frontend | 3000 | Next.js 16 PWA |
| API | 8000 | FastAPI backend |
| Qdrant | 6333 | Vector store |
| Redis | 6379 | Cache & rate limiting |

---

## Architecture

```
User (voice/text) → Next.js PWA (offline-capable)
         ↓                    ↕ IndexedDB cache
    FastAPI API          Service Worker
         ↓
  InputGuard (OWASP LLM Top 10)
         ↓
  Mode Supervisor (keyword classifier)
         ↓
  Hybrid Retrieval (Qdrant dense + BM25 + cross-encoder)
         ↓
  Abstention / Red-Flag Check
         ↓
  LLM Generation (Claude API / Qwen3-8B)
         ↓
  OutputGuard (PII redaction, grounding, disclaimer)
         ↓
  Response (with citations, triage, confidence)
```

### Tech Stack

- **Frontend**: Next.js 16.2.3 + React 19.2 + TypeScript + Zustand 5 + TanStack Query 5
- **Backend**: FastAPI + Qdrant v1.17 + Redis 7.4
- **LLM**: Claude Sonnet 4.6 (primary, prompt-cached) / Qwen3-8B (offline fallback)
- **Embeddings**: BAAI/bge-m3 (1024-dim, multilingual)
- **Reranker**: mxbai-rerank-base-v2 (optional)
- **Offline**: Service Worker + IndexedDB + Background Sync
- **Security**: OWASP LLM Top 10 guardrails, PII redaction, rate limiting

---

## Knowledge Base

Sourced from official Uganda Ministry of Health publications:

- **VHT Strategy & Operational Guidelines** (2022)
- **iCCM Protocol** — integrated Community Case Management
- **Essential Maternal and Newborn Clinical Care Guidelines** (2022/2025)
- **Uganda Clinical Guidelines** — NCDs, HIV, TB, malaria
- **UNEPI Immunization Schedule**

All knowledge is structured as JSON with metadata (mode, severity, topic,
guideline, section) for precise retrieval and citation.

---

## Ethical Framework

See [ETHICS.md](ETHICS.md) for the complete ethical analysis, including:

- Never-diagnose commitment
- Uganda Data Protection & Privacy Act (2019) compliance
- AI safety guardrails (input/output)
- Bias and fairness audit
- Responsible deployment checklist

**Core principle**: Musawo AI amplifies human health workers — it never
replaces them.

---

## Project Structure

```
Musawo/
├── README.md                  ← This file
├── ETHICS.md                  ← Deep ethical analysis
├── CLAUDE.md                  ← Architecture decisions
├── DEMO.md                    ← 3-minute demo script
├── .env.example               ← Environment configuration
├── docker-compose.yml         ← Full stack orchestration
├── backend/                   ← FastAPI health service
│   ├── app/
│   │   ├── main.py            ← API endpoints + middleware
│   │   ├── service.py         ← RAG orchestrator
│   │   ├── llm.py             ← Claude + Qwen3-8B dual backend
│   │   ├── retriever.py       ← Qdrant hybrid search
│   │   ├── guardrails.py      ← OWASP LLM Top 10 safety
│   │   ├── models.py          ← Pydantic schemas
│   │   └── agents/
│   │       ├── supervisor.py  ← Mode classifier
│   │       └── state.py       ← Routing state
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                  ← Next.js 16 PWA
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx       ← Main chat + triage UI
│   │   │   ├── layout.tsx     ← Root layout + PWA meta
│   │   │   └── globals.css    ← Earth-tone design system
│   │   ├── components/        ← ChatMessage, ModeSelector, MaternalTracker...
│   │   ├── store/             ← Zustand chat state
│   │   ├── hooks/             ← TanStack Query API hooks
│   │   └── lib/               ← IndexedDB, service worker
│   ├── public/
│   │   ├── manifest.json      ← PWA manifest
│   │   └── sw.js              ← Service worker
│   ├── package.json
│   └── Dockerfile
├── knowledge-base/            ← Official MoH guidelines (JSON)
│   ├── vht-guidelines/
│   ├── maternal-guidelines/
│   └── symptom-protocols/
└── scripts/
    └── reindex.sh             ← Knowledge base indexing
```

---

## Emergency Contacts (Uganda)

| Service | Number | Note |
|---------|--------|------|
| MoH Health Hotline | **0800 100 263** | Toll-free, 24/7 |
| National Ambulance | **0800 911 911** | Emergency |
| Poison Centre | +256-414-270-975 | |

---

## License

This project is built for the Claude Hackathon at Makerere University.
The knowledge base content is derived from publicly available Uganda
Ministry of Health publications.

## Acknowledgments

- Uganda Ministry of Health — VHT guidelines and maternal protocols
- WHO — Community Health Worker guidelines
- UNICEF — iCCM protocol development
- Makerere University School of Public Health
- Anthropic — Claude API with prompt caching and extended thinking
