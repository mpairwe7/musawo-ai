# 10. Testing — Musawo AI

## Backend (pytest)

```bash
cd backend && pip install -r requirements.txt
python -m pytest -q        # ~190 tests
```

Covers: API endpoints, guardrails (OWASP LLM Top-10, PII, crisis), supervisor +
agentic triage, retriever, service, voice VAD, **centralized config**
(`test_config.py`: defaults, type coercion, `extra=ignore`, `.env.example`
placeholder + drift guards), and the **LLM fallback chain** (`test_llm_fallback.py`:
Gemini → Groq → passages). A `conftest.py` autouse fixture blanks provider keys so
tests never hit a live API.

## Frontend (vitest)

```bash
cd frontend && npm ci
npm test            # parseSSE + useChatStore
npx tsc --noEmit    # typecheck
```

## Live regression — Playwright (API + browser E2E)

Runs against the **deployed Crane Cloud URL** (`E2E_BASE_URL`, default the prod URL):

```bash
cd frontend
npm run test:api    # API regression across every endpoint (no browser)
npm run test:e2e    # browser E2E (chromium)
npm run test:e2e:all
```

- **`e2e/api.spec.ts`** — every endpoint: health/ready/metrics, modes,
  emergency-contacts, facilities (+nearby distance sort), chat (structure +
  danger-sign escalation + 422), chat/stream SSE, triage (shape + injection
  blocked), feedback, session persistence, USSD. Side-effect-safe: SMS
  invalid-phone→400, webhook missing-body→400, and voice endpoints are
  **Sunbird-aware** (503 when unconfigured, 200/502 once configured). Retries
  absorb transient PaaS gateway blips.
- **`e2e/app.spec.ts`** — full stack (browser → `/api` → FastAPI → render): app
  loads, send→answer, and a regression guard that a comparison answer renders
  cleanly (no vertical-character collapse; the screenshot-bug guard).

Latest live run: **27/27 passing** (24 API + 3 browser).

## Lighthouse

```bash
cd frontend
CHROME_PATH=<chromium> npx lighthouse "$E2E_BASE_URL" \
  --only-categories=performance,accessibility,best-practices,seo --output=html
```

Latest live scores: **Performance 80 · Accessibility 96 · Best-Practices 100 · SEO 100**
(FCP 1.0s, LCP 3.6s, TBT 320ms, CLS 0.108).

## CI

- **`.github/workflows/deploy.yml`** — backend pytest + frontend typecheck/tests on
  every push/PR; build + push + Crane Cloud redeploy on `main`.
- **`.github/workflows/e2e.yml`** — Playwright (API + browser) + Lighthouse against
  the live URL, on demand (`workflow_dispatch`) and daily.
