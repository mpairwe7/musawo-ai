# 1. System Architecture — Musawo AI

Community Health Navigator for rural Uganda — offline-first, multilingual health guidance for VHTs, pregnant mothers, and community members.

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, Zustand 5, TanStack Query 5 |
| Backend | FastAPI, Python 3.11, uvicorn |
| LLM | Groq (llama-3.3-70b) → Claude → Local Qwen3 → Passages |
| Retrieval | BM25 keyword search (pre-indexed), Qdrant hybrid (when available) |
| Voice | Sunbird AI (STT/TTS/MT), energy-based VAD, WebSocket streaming |
| SMS/USSD | Twilio (SMS dispatch + USSD menus) |
| Process Mgr | supervisord (nginx + uvicorn + node) |
| Deployment | Docker → Docker Hub → Crane Cloud RENU |

## Data Flow

```
User (voice/text/SMS/USSD)
    ↓
nginx:8080 (reverse proxy)
    ├── / → Next.js:3000 (frontend UI)
    ├── /v1/* → uvicorn:8081 (FastAPI backend)
    └── /v1/voice/chat/stream → WebSocket (voice pipeline)

Backend Pipeline:
    Input → InputGuard → Supervisor (mode routing)
        → Cache lookup → BM25 retrieval
        → Abstention check → LLM (Groq/Claude)
        → OutputGuard → Response
```

## Deployment Architecture

```
Docker Hub: landwind/musawo-ai:latest
    ↓
Crane Cloud RENU cluster (Kubernetes)
    ↓
Pod: supervisord → nginx(:8080) + uvicorn(:8081) + node(:3000)
    ↓
Public URL: https://musawo-ai-*.renu-01.cranecloud.io
```

## Knowledge Base

18 clinical guideline categories from Uganda MoH:
- Emergency protocols, family planning, first aid
- HIV/TB adherence, immunization, maternal guidelines
- Mental health, neonatal care, nutrition (MIYCAN)
- Symptom protocols, childhood illness, chronic diseases
- Emergencies, infectious diseases, maternal/obstetric
- VHT guidelines, WASH prevention
