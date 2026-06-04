# LLM external egress on Crane Cloud / RENU — solution

**Status:** solved app-side. On the RENU pod, Gemini reaches the model through the
**Cloudflare AI Gateway** over Cloudflare's reachable edge; DNS is provided by an
app-side **DoH resolver**. Ported from AgriLink Uganda's investigation.

## The problem — a two-layer block

RENU pods have **two** independent egress restrictions that both surface as the
same `ConnectTimeout`:

| Layer | Finding | Handling |
|------|---------|----------|
| **1. DNS** | The pod has no working upstream resolver — external hostnames don't resolve. | `backend/app/doh_resolver.py` resolves via `https://1.1.1.1/dns-query`. It **auto-activates** when external DNS is detected broken (`auto_activate_if_dns_broken`), called early in `main.py`. No-op where DNS works (local dev / NITA-U). |
| **2. TCP/443 firewall** | With DNS fixed, providers *still* time out — outbound TCP/443 to provider IPs is firewalled. **Only Cloudflare's anycast edge is reachable.** | Route Gemini through the **Cloudflare AI Gateway** (which lives on Cloudflare's edge). Groq already works because `api.groq.com` is Cloudflare-fronted (pinned in `/etc/hosts`). Direct Gemini (Google IPs) is unreachable and fast-fails. |

What's reachable from the pod (IP-literal probe): Cloudflare anycast (`1.1.1.1`,
`104.16/13`, `172.64/13`, `172.65.x`) ✅; Google service IPs (`142.250.x`,
`172.217.x`) ❌. So pinning Gemini's own IPs does **not** work.

## The solution

**Gemini via the Cloudflare AI Gateway** (`backend/app/llm.py`). When
`CF_ACCOUNT_ID` + `CF_AI_GATEWAY` are set, the (sync) OpenAI client targets:

```
https://gateway.ai.cloudflare.com/v1/{CF_ACCOUNT_ID}/{CF_AI_GATEWAY}/compat/chat/completions
```

- model `google-ai-studio/<GEMINI_MODEL>` (unified-provider routing)
- `Authorization: Bearer <GEMINI_API_KEY>` (upstream Google key)
- `cf-aig-authorization: Bearer <CF_AIG_TOKEN>` (authorizes the gateway)
- `reasoning_effort: minimal` — the compat endpoint maps this to a zero thinking
  budget so Gemini 2.5+ doesn't spend `max_tokens` on hidden reasoning.

Because Musawo's Gemini client is **synchronous**, the DoH `socket.getaddrinfo`
patch applies to its resolution — `gateway.ai.cloudflare.com` resolves to its
**own** Cloudflare IP, so we connect to the host's real IP (no domain-fronting
403) with SNI/Host intact. (AgriLink needed a custom `_CFPinTransport` only
because its client is async and bypasses `getaddrinfo`.)

Provider chain: **Gemini (gateway when configured, else direct) → Groq → local →
passages.** Each tier fails fast (6–10 s connect, no retries) so a blocked path
demotes in seconds, never stalls.

## Configuration

```bash
GEMINI_API_KEY=...        # Google AI Studio key (the upstream provider)
CF_ACCOUNT_ID=...         # Cloudflare account id
CF_AI_GATEWAY=...         # AI Gateway name (e.g. an existing gateway in the account)
CF_AIG_TOKEN=...          # gateway authorization token (cf-aig-authorization)
```

Set as GitHub Actions secrets; the deploy workflow passes them to the Crane app
via `cranecloud apps update -e`. Leave the `CF_*` empty in environments with
normal egress to use the direct Gemini endpoint.

## Crane Cloud env-merge note

`cranecloud apps update -e KEY=val` **adds new keys but does not flip an already-set
key** (observed: `LLM_BACKEND` stays at its first value). This is harmless here —
the LLM chain keys off `GEMINI_API_KEY` presence, not `LLM_BACKEND`, and the DoH
resolver auto-activates regardless of any flag. Brand-new keys (`CF_*`,
`SUNBIRD_*`) are applied normally.

## Verifying

- `/health` → `200`, `llm_ready:true` (and `sunbird_ai:true` when Sunbird creds
  are set).
- `POST /v1/chat` returns in ~3–6 s when the gateway path is live (a ~16–26 s
  reply means Gemini is timing out and falling back to Groq — check `CF_*`).
- Cloudflare AI Gateway analytics show the Gemini traffic.

## Voice (STT/TTS) — same egress, via Workers AI

English voice has the identical RENU egress problem (`api.openai.com` for Whisper and
`edge-tts`'s host are firewalled), solved the same way — **Cloudflare Workers AI** over
the reachable edge (`api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{model}`), with
a Workers AI token (`CF_API_TOKEN`):

- **STT**: `@cf/openai/whisper-large-v3-turbo` (`CF_STT_MODEL`) — base64 audio in, transcript out (~1.5s).
- **TTS**: `@cf/myshell-ai/melotts` (`CF_TTS_MODEL`) — text in, base64 MP3 data URL out (~2.2s).

`backend/app/sunbird.py` tries these first for English (`speech_to_text` / `text_to_speech`),
then OpenAI/local; Ugandan languages stay on Sunbird. See [`06-voice-speech.md`](06-voice-speech.md).
