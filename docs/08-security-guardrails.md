# 8. Security & Guardrails — Musawo AI

## OWASP LLM Top 10 (2025) Compliance

| # | Risk | Mitigation |
|---|------|-----------|
| LLM01 | Prompt injection | InputGuard regex + spotlight markers on passages |
| LLM02 | Insecure output | OutputGuard + HTML escaping |
| LLM03 | Training data poisoning | Read-only knowledge base, no user-contributed content |
| LLM05 | Output handling | Structured JSON responses, no raw HTML |
| LLM06 | Excessive agency | No tool execution, read-only retrieval |
| LLM07 | System prompt leakage | Spotlight markers prevent extraction |
| LLM08 | Model denial of service | Rate limiting (slowapi), max input 2000 chars |
| LLM09 | Hallucination | Abstention threshold, grounding check, citation requirement |
| LLM10 | Overreliance | "Visit health facility" disclaimer on all responses |

## InputGuard

- **Injection detection**: regex patterns for common injection attacks
- **PII redaction**: Uganda health ID patterns (NIN, hospital numbers)
- **Max length**: 2000 characters
- **Red-flag escalation**: danger signs trigger immediate facility referral

## OutputGuard

- **Abstention threshold**: 0.05 (refuse if retrieval confidence below)
- **Escalation threshold**: 0.25 (flag for human review)
- **Grounding threshold**: 0.30 (warn if response not well-grounded)

## Privacy (Uganda Data Protection Act)

- `STORE_RAW_PROMPTS=false` — no raw query logging
- Conversation TTL: 7 days
- Feedback TTL: 90 days
- No PII in analytics pipeline
