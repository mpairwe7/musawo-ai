# Musawo AI — 3-Minute Demo Script `v2.3`

> **Category**: Biology & Physical Health
> **Tagline**: "Because every village health worker deserves a smart assistant."

---

## Setup (before demo)

```bash
cp .env.example .env
# Add: GROQ_API_KEY=gsk_... (free at console.groq.com)

# Option A: Docker
docker compose up -d
./scripts/reindex.sh
./scripts/demo-seed.sh

# Option B: Local dev
cd backend && GROQ_API_KEY=gsk_... uvicorn app.main:app --port 8888 &
cd frontend && INTERNAL_API_URL=http://localhost:8888 npx next dev --port 3200

# Open http://localhost:3200
```

---

## Demo Flow (3 minutes)

### 0:00–0:20 — Hook

> "In rural Uganda, 68,000 Village Health Teams are the first — and often
> only — point of health contact for millions of people. They still work
> from laminated cards printed in 2015.
>
> **Musawo AI** is their smart assistant. Offline-first. Multilingual.
> Powered by Groq's free LLM tier. And it never, ever diagnoses — it only guides."

**[Show the landing screen]** — Grok-inspired glassmorphism UI. Point out:
- Earth-tone warm design (not clinical white — culturally appropriate)
- Three mode cards: VHT Triage, Maternal Care, Community Health
- Emergency hotline always visible at the bottom
- Welcome empty state with gradient text

---

### 0:20–1:00 — VHT Triage Mode (the killer feature)

**[Click VHT Triage mode]**

**[Enable "Guided Assessment (iCCM Agent)" toggle]**

**Type:** "A 3-year-old child has fever, fast breathing, and cannot drink"

**[Point out as the response appears:]**

1. **Red REFER NOW triage card** pinned ABOVE the response text — danger signs
   detected BEFORE the LLM generates anything (hard-coded regex, not AI):
   - "Cannot drink" → general danger sign
   - "Convulsions" → general danger sign

2. **Voice alert** — the system SPEAKS the danger signs aloud:
   *"Danger signs detected! Go to the health facility immediately!"*

3. **Emergency call button** pulses red — one tap to call 0800 100 263

4. **## Structured response**: Assessment → Guidance → When to Refer
   with **bold drug names** and exact dosages from UCG 2016

5. **Citations**: Expandable sources showing "UCG 2016 Section 17.4 — iCCM"

**[Now ask a follow-up:]** "What if the RDT is positive?"

> "Notice: Musawo REMEMBERS the child from the previous turn. It knows we're
> still talking about the same 3-year-old with fever. It gives the ACT dosage
> for 12-59 months: 2 tablets twice daily for 3 days."

---

### 1:00–1:40 — Maternal Care Mode

**[Switch to Maternal Care mode]**

**[Set pregnancy week to 28]** — Watch the tracker update:
- Third trimester badge
- Progress bar (70%)
- Next milestone: "Fifth ANC Visit at Week 30"
- Danger signs always expandable

**Type in Luganda:** "Omwana wange tayonsa bulungi"
*(My baby isn't breastfeeding well)*

**[Point out:]**
- Response in **## Assessment / ## Guidance** format
- **Bold** key terms: "exclusive breastfeeding", "colostrum"
- Citations from MoH Essential Maternal Guidelines 2022
- Gentle, supportive tone

> "Musawo responds in the language the mother writes in. No settings to
> change — it just works. And every response has a disclaimer."

---

### 1:40–2:20 — Clinic Finder + Offline Mode

**[Open Clinic Finder]** (map pin icon in header)

**[Point out:]**
- Embedded OpenStreetMap with your GPS location
- Facilities sorted by distance: "Mulago NRH — 2.3 km"
- One-tap "Call" and "Directions" (opens Google Maps)
- Facility services listed

**[Toggle browser offline]** (DevTools → Network → Offline)

**[Type:]** "My child has diarrhoea"

**[Point out:]**
- Prominent **offline banner** with emergency number
- Response served from IndexedDB cache
- "Your message has been saved and will be sent when you reconnect"

**[Go online, type:]** "Prescribe me antibiotics"

> "Blocked. Musawo refuses to prescribe, diagnose, or provide harmful advice."

---

### 2:20–2:50 — The Architecture

**[Show briefly — can use CLAUDE.md:]**

- **3-tier LLM**: Groq (free, 500 tok/s) -> Claude -> Passage-based
- **10-turn conversation memory**: Deep clinical discussions
- **Agentic triage**: Multi-step Assess->Classify->Treat/Refer
- **203 clinical entries** across 20 knowledge base files (immunization, FP, HIV/TB, WASH, first aid, mental health, GBV + more)
- **10 inline SVG diagrams**: Auto-detected from content (danger signs, ORS prep, RDT, fever assessment, etc.)
- **Voice interaction**: Floating modal with waveform + 5 voice personas (gender/language matching)
- **Accessibility**: TTS toggle, 3-level font size, high contrast mode, localized danger signs (4 languages)
- **Multi-session sidebar**: Search, export, session switching, auto-titling
- **4-language starter prompts**: English, Luganda, Runyankole, Swahili
- **OWASP LLM Top 10**: Injection guards, PII redaction, grounding
- **Installable PWA**: Service Worker + IndexedDB + background sync + skeleton loading
- **Twilio SMS + USSD**: Feature phone VHTs can text or dial health questions
- **Prometheus metrics**: Query volume, triage severity, latency histograms — fully wired
- **172 tests**: 149 pytest + 23 vitest — guardrails, triage agent, API, retriever, LLM, service, store

> "We forked our production URA Chatbot — the security, guardrails, and
> RAG pipeline are battle-tested. We added Groq for free LLM access,
> agentic triage, inline health diagrams, and Grok-inspired chat UX."

---

### 2:50–3:00 — Close

> "68,000 VHTs. 1.4 million births per year. 16 maternal deaths per day.
>
> Musawo AI won't solve all of this. But it can make sure that when a
> village health worker stands in a home with a sick child at midnight,
> they have more than a laminated card from 2015.
>
> Musawo — your community health navigator."

**[Show ETHICS.md briefly]** — Uganda Data Protection Act compliance,
never-diagnose commitment, responsible deployment checklist.

---

## Backup Demos (for Q&A)

### Multi-Turn Deep Conversation
```
"A 2-year-old has malaria, RDT positive. ACT dosage?"
→ "2 tablets twice daily for 3 days"

"Same child also has diarrhoea"
→ "Give ORS + Zinc 20mg daily for 10 days"

"Should I refer or treat at home?"
→ Synthesizes: "Treat both at home — ACT + Amoxicillin. Refer if danger signs."
```

### USSD Demo (Feature Phones)
```bash
curl -X POST localhost:8888/v1/ussd/callback -d "text=1*1"
→ "FEVER: Do RDT, if positive give ACT..."
```

### Community Mode
- "Where is the nearest health centre?" → GPS-sorted facility list with map
- "What are the symptoms of diabetes?" → UCG 2016 Section 8.1.3

### Inline Health Diagrams
- "How do I prepare ORS?" -> Response + auto-detected ORS preparation diagram (4-step visual)
- "What are the danger signs in children?" -> Response + danger signs diagram (6 icons)
- "What vaccines does my baby need?" -> Response + immunization schedule timeline
- The diagrams are inline SVGs — work fully offline, no network requests

### Multi-Session Demo
- Send a message -> session auto-created in sidebar
- Click hamburger menu -> see conversation list with dates + mode badges
- Click "New Chat" -> start fresh while preserving history
- Switch back to old session -> full context restored

### Voice Interaction (v2.3 — hackathon highlight)
- Tap the mic button -> floating voice modal opens with green pulsing orb
- Speak -> real-time waveform animation + live transcription
- Tap green "Send" to approve, or red "Cancel" to discard
- Open Voice Settings (speaker icon in header) -> select voice persona
- Pick "Swahili Male" -> preview plays sample -> close -> TTS uses selected voice
- On any Musawo message, tap the speaker icon -> reads response aloud

### Accessibility Settings (v2.3)
- Open Settings (gear icon) -> toggle "Voice Output (TTS)" off -> no more auto-speak
- Change Font Size to "Large" -> all chat text scales up
- Enable "High Contrast" -> background goes pure black, text/borders brighten
- Version number displayed at bottom of settings

### Conversation Export (v2.3)
- Hover a session in sidebar -> click download icon -> .txt file downloads
- File includes timestamps, roles, full content

### New Malaria RDT Diagram (v2.3)
- Type: "How do I use an RDT to test for malaria?"
- Response includes auto-detected `malaria_rdt` diagram
- Shows 4-step process: Clean Finger -> Prick & Collect -> Add Buffer -> Wait 15 min
- Bottom shows result interpretation: 1 line = Negative, 2 lines = Positive

### Collapse + Clear Chat
- Long response -> click "Collapse" to minimize
- Trash icon -> "Clear all messages?" -> fresh start

### 4-Language Support
- Switch locale to "LG" -> Luganda starter prompts appear
- Switch to "NY" -> Runyankole prompts
- Switch to "SW" -> Swahili prompts
- Send in Luganda -> response comes back in Luganda with English medical terms
