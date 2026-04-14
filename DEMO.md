# Musawo AI — 3-Minute Demo Script

> **Category**: Biology & Physical Health
> **Tagline**: "Because every village health worker deserves a smart assistant."

---

## Setup (before demo)

```bash
cp .env.example .env        # Add your ANTHROPIC_API_KEY
docker compose up -d         # Start all services (~2 min first time)
./scripts/reindex.sh         # Index health knowledge base
open http://localhost:3000   # Open in browser
```

---

## Demo Flow (3 minutes)

### 0:00–0:20 — Hook

> "In rural Uganda, 68,000 Village Health Teams are the first — and often
> only — point of health contact for millions of people. They still work
> from laminated cards printed in 2015.
>
> **Musawo AI** is their smart assistant. Offline-first. Multilingual.
> And it never, ever diagnoses — it only guides."

**[Show the landing screen]** — Earth-tone glassmorphism UI with three
mode cards. Point out the emergency hotline always visible at the bottom.

---

### 0:20–1:00 — VHT Triage Mode (the killer feature)

**[Click VHT Triage mode]**

**Type or speak:** "A 3-year-old child has fever, fast breathing, and is not able to drink"

**[Point out as the response streams:]**

1. **Red REFER NOW triage card** appears immediately — before the full
   response even finishes. The system detected three danger signs:
   - "Not able to drink" (general danger sign)
   - "Fast breathing" (possible pneumonia)
   - "Fever" (possible malaria)

2. **Emergency call button** pulses red — one tap to call the health hotline.

3. **Step-by-step guidance**: The response follows iCCM protocol —
   "Give first dose of ACT, begin ORS, and REFER IMMEDIATELY."

4. **Confidence badge**: Shows HIGH confidence — grounded in official
   MoH iCCM guidelines.

5. **Citations**: Expandable sources showing exactly which guideline
   section each recommendation comes from.

> "Notice: the danger sign detection runs BEFORE the AI generates text.
> Hard-coded pattern matching ensures we never miss a red flag."

---

### 1:00–1:40 — Maternal Care Mode (the heart)

**[Switch to Maternal Care mode]**

**[Set pregnancy week to 28]** — Watch the tracker update:
- Third trimester badge
- Progress bar (70%)
- Next milestone: "Fifth ANC Visit at Week 30"

**[Expand Danger Signs]** — Always visible, always in view.

**Type in Luganda:** "Omwana wange tayonsa bulungi"
*(My baby isn't breastfeeding well)*

**[Point out:]**
- Response comes back **in Luganda** with English medical terms explained
- Gentle, supportive tone (many users are young first-time mothers)
- Practical advice from MoH breastfeeding guidelines
- "If difficulties continue, visit the nearest health facility"

> "Musawo responds in the language the mother writes in. No settings to
> change — it just works."

---

### 1:40–2:20 — Offline Mode & Ethical Guardrails

**[Toggle browser to offline mode]** (DevTools → Network → Offline)

**Type:** "My child has diarrhoea, what should I do?"

**[Point out:]**
- **Offline badge** appears in the header
- Response served from **IndexedDB cache** — previously cached knowledge
- Message: "You are offline. Your message has been saved."
- Emergency number still visible and tappable (works via cellular)

**[Go back online, then type:]** "Prescribe me antibiotics for my cough"

**[Point out the guardrail response:]**
- "I can only provide health guidance — I cannot prescribe medication.
  Please consult a qualified health worker."

> "Musawo refuses to prescribe, diagnose, or provide harmful advice.
> Every response includes a disclaimer and a path to human help."

---

### 2:20–2:50 — The Architecture That Makes It Work

**[Quick architecture overview — can show CLAUDE.md or a diagram:]**

- **Hybrid RAG**: Dense embeddings (bge-m3) + BM25 sparse + cross-encoder
  reranking — same proven architecture from our original RAG system.
- **Dual LLM**: Claude API (primary, with prompt caching) + Qwen3-8B
  (offline fallback on local GPU).
- **OWASP LLM Top 10**: Prompt injection guards, PII redaction (Uganda-specific:
  NIN, phone, HIV status), output grounding.
- **PWA**: Service worker + IndexedDB = works without internet.
- **Voice-first**: Web Speech API in Luganda, Runyankole, Swahili, English.

> "We forked our production URA Chatbot — the security, guardrails, and
> RAG pipeline are battle-tested. We added health-specific knowledge,
> triage logic, and the maternal companion."

---

### 2:50–3:00 — Close

> "68,000 VHTs. 1.4 million births per year. 16 maternal deaths per day.
>
> Musawo AI won't solve all of this. But it can make sure that when a
> village health worker stands in a home with a sick child at midnight,
> they have more than a laminated card from 2015.
>
> Musawo — your community health navigator."

**[Show the ETHICS.md briefly]** — Point out Uganda Data Protection Act
compliance, the never-diagnose commitment, and the responsible deployment
checklist.

---

## Backup Demos (if time permits or for Q&A)

### Community Mode
- "Where is the nearest health centre?" → Shows facility list with
  phone numbers
- "What are the symptoms of diabetes?" → Grounded guidance from Uganda
  Clinical Guidelines

### Voice Input
- Click mic → Speak in Luganda → Watch transcription → Health guidance
  returned in Luganda

### Locale Switching
- Switch to Runyankole (NY) → All placeholders, prompts, and responses
  adapt instantly
