#!/usr/bin/env bash
###############################################################################
# DataStack Compass — Infrastructure Health Check
# Usage: bash health_check.sh
###############################################################################
set -e

# ── Colors ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

PASS="${GREEN}${BOLD}PASS${RESET}"
FAIL="${RED}${BOLD}FAIL${RESET}"

total=0
passed=0

DOCKER_CMD="docker"
if command -v docker.exe >/dev/null 2>&1; then
  DOCKER_CMD="docker.exe"
fi

# ── Helper ───────────────────────────────────────────────────────────────────
check() {
  local name="$1"
  shift
  total=$((total + 1))

  if "$@" > /dev/null 2>&1; then
    printf "  %-22s %b\n" "$name" "$PASS"
    passed=$((passed + 1))
  else
    printf "  %-22s %b\n" "$name" "$FAIL"
  fi
}

# ── Banner ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════╗${RESET}"
echo -e "${CYAN}${BOLD}║       DataStack Compass — Health Check          ║${RESET}"
echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════╝${RESET}"
echo ""

# ── 1. MinIO (S3 API) ───────────────────────────────────────────────────────
echo -e "${BOLD}▸ Storage Layer${RESET}"
check "MinIO (S3 API)" \
  curl -sf --max-time 5 http://localhost:9000/minio/health/live

check "MinIO (Console)" \
  curl -sf --max-time 5 -o /dev/null -w '' http://localhost:9001

# ── 2. StarRocks (MySQL protocol) ───────────────────────────────────────────
echo ""
echo -e "${BOLD}▸ OLAP Layer${RESET}"
check "StarRocks (MySQL)" \
  $DOCKER_CMD exec datastack-starrocks mysql -h 127.0.0.1 -P 9030 -u root --skip-column-names -e "SELECT 1"

check "StarRocks (FE HTTP)" \
  curl -sf --max-time 5 -o /dev/null http://localhost:8030/api/health

# ── 3. Airflow ──────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}▸ Orchestration Layer${RESET}"
check "Airflow Webserver" \
  curl -sf --max-time 5 http://localhost:8080/health

check "Postgres (Airflow DB)" \
  $DOCKER_CMD exec datastack-postgres pg_isready -U airflow -q

# ── 4. Application Layer ────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}▸ Application Layer${RESET}"
check "FastAPI Backend" \
  curl -sf --max-time 5 http://localhost:8000/health

check "Frontend (React)" \
  curl -sf --max-time 5 -o /dev/null http://localhost:3000

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "──────────────────────────────────────────────────"
if [ "$passed" -eq "$total" ]; then
  echo -e "  Result: ${GREEN}${BOLD}${passed}/${total} services healthy ✓${RESET}"
else
  echo -e "  Result: ${RED}${BOLD}${passed}/${total} services healthy ✗${RESET}"
  exit 1
fi

# # ── 5. Docker Memory Usage ──────────────────────────────────────────────────
# echo ""
# echo -e "${BOLD}▸ Docker Memory Usage${RESET}"
# echo ""
# $DOCKER_CMD stats --no-stream --format "table {{.Container}}\t{{.MemUsage}}\t{{.MemPerc}}" \
#   | grep -E "datastack-|CONTAINER" || echo "  (no datastack containers running)"

# echo ""
