# Musawo AI — Ethics & Safety Framework

> "First, do no harm." — Adapted for AI health systems in resource-limited settings.

---

## 1. Ethical Position

Musawo AI is a **health guidance assistant**, not a diagnostic tool, not a
doctor, and not a replacement for the Ugandan health system. It exists to
**amplify** the reach of Village Health Teams and community health structures
— never to replace human clinical judgement.

### Core Ethical Commitments

| Principle | Implementation |
|-----------|---------------|
| **Non-maleficence** | Never diagnose or prescribe. Always show confidence level. Mandatory escalation path for danger signs. |
| **Beneficence** | Grounded in official MoH guidelines. Designed to reduce the 68,000+ VHT knowledge gap (still using 2015 laminated cards). |
| **Autonomy** | User always controls the interaction. Clear disclosure that this is AI. Easy exit to human help at every point. |
| **Justice** | Multilingual (Luganda, Runyankole, Swahili, English). Offline-first for areas without connectivity. SMS/USSD fallback for feature phones. Low-literacy UI design. |
| **Transparency** | Sources cited for every response. Confidence levels shown. Open-source. |

---

## 2. Risk Analysis

### 2.1 High-Risk Scenarios

| Risk | Severity | Mitigation |
|------|----------|-----------|
| **Misclassification of danger signs** | Critical | Red-flag pattern detection runs BEFORE LLM. Hard-coded danger sign checklist from iCCM protocol. Any match → immediate REFER NOW. |
| **Delayed care-seeking** | Critical | Every response includes "visit facility if symptoms worsen" disclaimer. Emergency hotline visible at all times. Escalation banner for low-confidence responses. |
| **Over-reliance / trust calibration** | High | Confidence badges (HIGH/MEDIUM/LOW) on every response. Abstention when retrieval confidence < 0.15. Never uses authoritative language ("you have X"). |
| **PII exposure** | High | Uganda-specific PII patterns redacted (NIN, phone, HIV status, ART numbers). Prompts never stored by default (NDPA §19). No user accounts required. |
| **Hallucinated medical advice** | High | Grounding check (faithfulness score). Abstention if context insufficient. Passage spotlight markers prevent prompt injection. |
| **Cultural harm** | Medium | Reviewed with Ugandan health workers. Respectful language. No assumptions about literacy, religion, or family structure. Luganda-first design. |
| **Gender bias** | Medium | Maternal mode avoids patronizing language. Acknowledges diverse family structures. Includes male partner engagement guidance per MoH guidelines. |

### 2.2 What Musawo CANNOT Do

- Diagnose any medical condition
- Prescribe, recommend, or change medication dosages
- Replace a clinical examination
- Provide emergency medical services
- Guarantee accuracy of any health guidance
- Store or transmit personally identifiable health information

---

## 3. Uganda Data Protection & Privacy Act (2019) Compliance

The Uganda Data Protection and Privacy Act (NDPA) and its regulations
govern how personal data — including health data — must be handled.

### Compliance Measures

| NDPA Provision | Musawo Implementation |
|----------------|----------------------|
| **§3 — Lawful processing** | No personal data collected by default. Conversations stored locally on-device (IndexedDB). Server-side: `STORE_RAW_PROMPTS=false`. |
| **§7 — Consent** | No user registration required. Optional features (pregnancy tracker) are opt-in. Clear informed consent before any data is saved. |
| **§19 — Data minimization** | Only query text sent to server. PII auto-redacted before processing. No names, phone numbers, or health IDs stored. |
| **§24 — Data security** | TLS in transit. No at-rest PII storage. Rate limiting prevents abuse. Input/output guardrails prevent injection. |
| **§26 — Health data (special category)** | HIV status patterns auto-redacted. Health responses are generic guidance, not linked to individuals. Audit trail for compliance. |
| **§28 — Privacy Impact Assessment** | This document serves as the PIA. Risk register maintained above. |
| **§35 — Cross-border transfers** | When using Claude API, query text (with PII redacted) is sent to Anthropic's servers. Local model mode (Qwen3-8B) keeps all data on-premise. |
| **§43 — Right to erasure** | No persistent personal data stored server-side. Client-side data clearable via browser. |

### Data Flow

```
User → [PII Redaction] → Server → [Guardrails] → LLM → [Output Guard] → User
         (client)                                          (server)
         
No PII leaves the device. Only redacted query text reaches the server.
Health responses are generic guidance, not personal medical records.
```

---

## 4. AI Safety Guardrails

### Input Safety (OWASP LLM Top 10 2025)

- **LLM01 — Prompt Injection**: 11+ regex patterns block direct injection.
  Retrieved passages scrubbed for indirect injection via `scan_retrieved_text()`.
- **LLM02 — Sensitive Data**: PII auto-redacted (email, phone, NIN, HIV status,
  ART numbers, credit cards, passports).
- **LLM03 — Supply Chain**: `trust_remote_code=false` for local models.
  Model revisions pinned to specific commits.

### Output Safety

- **Abstention**: Refuses to answer if retrieval confidence < 0.15.
- **Grounding**: Faithfulness score computed against source passages.
  Warning appended if score < 0.3.
- **Prompt Leakage**: Output checked for system prompt regurgitation.
- **Mandatory Disclaimer**: Every response includes "This is guidance only —
  not a medical diagnosis."
- **Crisis Escalation**: Suicide/self-harm queries immediately redirect to
  Uganda Mental Health Hotline (0800 100 263).

### Ethical Escalation Path

```
User Query
    │
    ├── Danger sign detected? → IMMEDIATE: "REFER NOW" + hotline number
    ├── Crisis/self-harm?     → IMMEDIATE: Mental health hotline
    ├── Low confidence?       → "I don't have enough information" + facility referral
    ├── Harmful request?      → Block + explain limitations
    └── Normal query          → Guidance + confidence + sources + disclaimer
```

---

## 5. Bias and Fairness Audit

### Known Biases and Mitigations

| Bias Source | Description | Mitigation |
|-------------|-------------|-----------|
| **Training data** | LLM trained primarily on English text; Luganda medical terminology underrepresented | Knowledge base in English with Luganda translations. System prompt instructs code-switching. Multilingual embedding model (bge-m3). |
| **Urban/rural** | Most health data from urban facilities | Knowledge base specifically sources MoH VHT guidelines designed for community-level care. |
| **Gender** | Risk of reinforcing traditional gender roles in health-seeking | Inclusive language. Maternal mode designed with women's autonomy as core principle. |
| **Age** | Risk of ageism in triage recommendations | iCCM protocols apply equally. Dosage guidance age-specific per MoH standards. |
| **Socioeconomic** | Assumes smartphone access | SMS/USSD fallback via Africa's Talking. Offline mode with cached responses. Voice-first for low-literacy users. |

---

## 6. Responsible Deployment

### Pre-deployment Checklist

- [ ] Clinical review by qualified Ugandan health worker
- [ ] User testing with actual VHTs in at least 3 districts
- [ ] Luganda translation verified by native speakers
- [ ] Red-flag detection validated against 100+ danger sign scenarios
- [ ] Offline mode tested in low-connectivity environments
- [ ] Data protection compliance reviewed by legal counsel
- [ ] Emergency hotline numbers verified as current and operational
- [ ] Feedback loop established with MoH district health teams

### Monitoring and Continuous Improvement

- Escalation rate tracking (high escalation → review guidelines)
- User feedback analysis (thumbs up/down + comments)
- Faithfulness score distribution (detect grounding degradation)
- Red-flag detection accuracy (false positive/negative tracking)
- Monthly review of knowledge base against latest MoH publications

---

## 7. Statement of Limitations

Musawo AI is an experimental technology demonstration. It has NOT been:

- Clinically validated through randomized controlled trials
- Approved by any medical regulatory authority
- Tested at scale with real patients

**It should NEVER be used as the sole basis for any health decision.**

The developers are committed to responsible AI development and welcome
feedback from health professionals, ethicists, and community members.

---

*This ethics framework follows the WHO Ethics and Governance of AI for
Health (2021) guidelines and the Uganda National Council for Science and
Technology ethical review framework.*
