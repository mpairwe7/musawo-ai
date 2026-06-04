#!/usr/bin/env bash
# Musawo AI — post-deploy smoke test.
# Exercises the public surface end-to-end (browser → nginx → uvicorn → response).
#
# Usage:
#   ./scripts/smoke.sh [BASE_URL]
# Examples:
#   ./scripts/smoke.sh                                   # default: production
#   ./scripts/smoke.sh http://localhost:8080             # local container
#   ./scripts/smoke.sh https://musawo-ai-ce243528.renu-01.cranecloud.io
set -uo pipefail

BASE="${1:-https://musawo-ai-ce243528.renu-01.cranecloud.io}"
PASS=0 FAIL=0
say()  { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; FAIL=$((FAIL+1)); }

say "Target: $BASE"

# 1. /health → 200 with status + version
say "GET /health"
body="$(curl -fsS --max-time 20 "$BASE/health" 2>/dev/null)" \
  && echo "$body" | grep -q '"status"' \
  && ok "/health 200 ($(echo "$body" | tr -d ' \n' | cut -c1-80)…)" \
  || bad "/health did not return a healthy JSON body"

# 2. /ready → 200 (may be 503 while warming; retry a few times)
say "GET /ready"
ready=0
for i in 1 2 3 4 5; do
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$BASE/ready")"
  [ "$code" = "200" ] && { ready=1; break; }
  sleep 3
done
[ "$ready" = "1" ] && ok "/ready 200" || bad "/ready not ready after retries (last=$code)"

# 3. /v1/chat → 200 with a non-empty answer
say "POST /v1/chat"
chat="$(curl -fsS --max-time 60 -H 'Content-Type: application/json' \
  -d '{"query":"A 3-year-old has fever and tested positive on RDT","mode":"vht"}' \
  "$BASE/v1/chat" 2>/dev/null)" \
  && echo "$chat" | grep -q '"answer"' \
  && ok "/v1/chat returned an answer" \
  || bad "/v1/chat failed or returned no answer"

# 4. /v1/chat/stream → SSE frames then completion
say "POST /v1/chat/stream (SSE)"
stream="$(curl -fsS --max-time 60 -N -H 'Content-Type: application/json' -H 'Accept: text/event-stream' \
  -d '{"query":"What is the ORS dosage for a child?","mode":"vht"}' \
  "$BASE/v1/chat/stream" 2>/dev/null)" \
  && echo "$stream" | grep -q 'data:' \
  && ok "/v1/chat/stream emitted SSE data frames" \
  || bad "/v1/chat/stream produced no SSE frames"

# 5. /v1/modes → 3 modes
say "GET /v1/modes"
curl -fsS --max-time 20 "$BASE/v1/modes" 2>/dev/null | grep -qiE 'vht|maternal|community' \
  && ok "/v1/modes returned modes" \
  || bad "/v1/modes did not list modes"

say "Result: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
