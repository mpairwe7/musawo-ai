#!/usr/bin/env bash
# =============================================================================
# Musawo AI — Demo Seed Script
#
# Prepares the system for a live demo by:
# 1. Verifying all services are healthy
# 2. Indexing the knowledge base into Qdrant
# 3. Running a quick smoke test
# 4. Printing demo-ready status
#
# Usage: ./scripts/demo-seed.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

API_URL="${API_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3000}"

info()  { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[FAIL]${NC} $*" >&2; }
step()  { echo -e "\n${CYAN}${BOLD}── $* ──${NC}"; }

# ── Step 1: Health checks ──────────────────────────────────────────────

step "Checking services"

if curl -sf "${API_URL}/health" > /dev/null 2>&1; then
    info "API is healthy at ${API_URL}"
else
    error "API not reachable at ${API_URL}"
    echo "  Run: docker compose up -d"
    exit 1
fi

if curl -sf "${FRONTEND_URL}" > /dev/null 2>&1; then
    info "Frontend is healthy at ${FRONTEND_URL}"
else
    warn "Frontend not reachable (may still be building)"
fi

# ── Step 2: Check Qdrant ───────────────────────────────────────────────

step "Checking Qdrant vector store"

QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
if curl -sf "${QDRANT_URL}/healthz" > /dev/null 2>&1; then
    info "Qdrant is healthy"
else
    error "Qdrant not reachable — run: docker compose up qdrant"
    exit 1
fi

# ── Step 3: Index knowledge base ───────────────────────────────────────

step "Indexing knowledge base"

if [ -f "./scripts/reindex.sh" ]; then
    bash ./scripts/reindex.sh
    info "Knowledge base indexed"
else
    warn "reindex.sh not found — skipping"
fi

# ── Step 4: Smoke tests ────────────────────────────────────────────────

step "Running smoke tests"

# Test modes endpoint
MODES=$(curl -sf "${API_URL}/v1/modes" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
if [ "${MODES}" = "3" ]; then
    info "Modes endpoint: 3 modes (vht, maternal, community)"
else
    error "Modes endpoint returned ${MODES} modes (expected 3)"
fi

# Test facilities endpoint
FACILITIES=$(curl -sf "${API_URL}/v1/facilities" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
info "Facilities loaded: ${FACILITIES}"

# Test triage endpoint
TRIAGE=$(curl -sf -X POST "${API_URL}/v1/triage" \
    -H "Content-Type: application/json" \
    -d '{"query":"child has fever and convulsions","mode":"vht","locale":"en"}' \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('phase','unknown'))" 2>/dev/null || echo "error")
if [ "${TRIAGE}" != "error" ]; then
    info "Triage endpoint: phase=${TRIAGE}"
else
    warn "Triage endpoint not responding"
fi

# Test emergency contacts
HOTLINE=$(curl -sf "${API_URL}/v1/emergency-contacts" | python3 -c "import sys,json; print(json.load(sys.stdin)['health_hotline']['number'])" 2>/dev/null || echo "")
if [ "${HOTLINE}" = "0800 100 263" ]; then
    info "Emergency contacts: hotline=${HOTLINE}"
else
    warn "Emergency contacts endpoint issue"
fi

# Test metrics
METRICS=$(curl -sf "${API_URL}/metrics" | head -1 2>/dev/null || echo "")
if [ -n "${METRICS}" ]; then
    info "Prometheus metrics endpoint active"
else
    warn "Metrics endpoint not responding"
fi

# ── Step 5: Demo ready ─────────────────────────────────────────────────

step "DEMO READY"

echo ""
echo -e "${GREEN}${BOLD}Musawo AI is ready for demo!${NC}"
echo ""
echo -e "  Frontend:  ${CYAN}${FRONTEND_URL}${NC}"
echo -e "  API:       ${CYAN}${API_URL}${NC}"
echo -e "  Metrics:   ${CYAN}${API_URL}/metrics${NC}"
echo ""
echo -e "  ${BOLD}Demo script:${NC} See DEMO.md for the 3-minute walkthrough"
echo ""
echo -e "  ${BOLD}Key demo flows:${NC}"
echo "    1. VHT Triage: 'child has fever, fast breathing, cannot drink'"
echo "    2. Maternal: Set week 28, ask in Luganda about breastfeeding"
echo "    3. Offline: Toggle network off, send message, see cached response"
echo "    4. Clinic Finder: Open map, see nearest facilities with GPS"
echo "    5. Agentic Assessment: Enable iCCM Agent toggle, step through protocol"
echo ""
