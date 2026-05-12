# 2. Backend Setup — Musawo AI

FastAPI backend serving health guidance via RAG pipeline.

## Endpoints (22 total)

### Health & Monitoring
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service status, LLM readiness, version |
| GET | `/ready` | Readiness probe (503 if not ready) |
| GET | `/metrics` | Prometheus metrics |

### Chat & Triage
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/chat` | Single-shot RAG response |
| POST | `/v1/chat/stream` | SSE streaming response |
| POST | `/v1/triage` | Multi-step iCCM triage assessment |
| GET | `/v1/modes` | Available modes (VHT, Maternal, Community) |
| GET | `/v1/session/{id}/history` | Conversation history |
| POST | `/v1/feedback` | User feedback submission |

### Facilities & Emergency
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/facilities` | Health facility lookup (district/level filter) |
| GET | `/v1/facilities/nearby` | GPS-based nearest facility |
| GET | `/v1/emergency-contacts` | MoH hotline, ambulance, poison centre |

### Voice & Language
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/voice/stt` | Sunbird speech-to-text |
| POST | `/v1/voice/tts` | Sunbird text-to-speech |
| POST | `/v1/translate` | Language translation |
| POST | `/v1/detect-language` | Auto language detection |
| WS | `/v1/voice/chat/stream` | Streaming voice chat |

### SMS/USSD
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/sms/send` | Send SMS via Twilio |
| POST | `/v1/sms/webhook` | Incoming SMS handler |
| POST | `/v1/ussd/callback` | USSD menu navigation |

## Service Layer

**HealthService** (`service.py`) — core orchestrator:
1. Input guard (injection, PII)
2. Session management (thread-safe)
3. Facility query shortcut
4. Supervisor routing (VHT/Maternal/Community)
5. Query rewriting (abbreviations, typos, coreferences)
6. Dual retrieval (BM25 + cross-mode fallback)
7. Corrective RAG (re-retrieve if quality low)
8. Clarification check (ambiguous queries)
9. Abstention check (low confidence → refuse)
10. LLM generation (Groq → Claude → Local → Passages)
11. Output guard (hallucination check)

## Retrieval Pipeline

- **BM25 keyword search**: pre-indexed 20 knowledge base docs (4353 terms)
- **Qdrant hybrid** (when available): dense (BGE-M3) + sparse (BM25) + RRF fusion
- **Corrective RAG**: re-retrieves if initial quality score < threshold
- **Cross-mode fallback**: searches other modes if primary mode returns weak results
