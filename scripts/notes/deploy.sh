#!/usr/bin/env bash
# Build and start the Notes deployment (Garden compose + docker-compose.notes.yml).
# Same steps as scripts/plane-garden/deploy.sh, with two differences:
#   - images are built one at a time, so a 2 vCPU / 8 GB server does not run out of memory;
#   - the Garden-only instance finalize step runs only when GARDEN_AUTH_ENABLED=1.
# Usage: bash scripts/notes/deploy.sh /opt/notes/.env.notes
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$(realpath -m "${1:?Usage: deploy.sh <env file>}")"
cd "$ROOT_DIR/plane-community"

compose() {
  docker compose --env-file "$ENV_FILE" -f docker-compose.garden.yml -f docker-compose.notes.yml "$@"
}

env_value() {
  awk -v key="$1" '$0 !~ /^[[:space:]]*#/ { p = index($0, "="); if (p > 0 && substr($0, 1, p - 1) == key) { print substr($0, p + 1); exit } }' "$ENV_FILE"
}

compose config --quiet

if [[ "${NOTES_SKIP_BUILD:-0}" != "1" ]]; then
  echo "[notes] Building images one at a time..."
  for svc in api proxy live space web; do
    echo "[notes] build $svc ($(date +%T))"
    compose build "$svc"
  done
fi

echo "[notes] Starting state services..."
compose up -d plane-db plane-redis plane-mq plane-minio

echo "[notes] Waiting for object storage..."
for i in $(seq 1 40); do
  if compose run --rm --no-deps proxy curl -fsS http://plane-minio:9000/minio/health/live >/dev/null 2>&1; then break; fi
  [[ "$i" == 40 ]] && { compose ps; echo "[notes] Object storage did not become ready." >&2; exit 1; }
  sleep 3
done

echo "[notes] Running migrations..."
compose up --abort-on-container-exit --exit-code-from migrator migrator

echo "[notes] Starting application services..."
compose up -d --remove-orphans api worker beat-worker live web space proxy

echo "[notes] Waiting for API readiness..."
for i in $(seq 1 40); do
  if compose exec -T api python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:8000' + os.environ.get('NOTES_API_HEALTH_PATH', '/auth/firebase/health/'), timeout=3).read()" >/dev/null 2>&1; then break; fi
  [[ "$i" == 40 ]] && { compose ps; echo "[notes] API did not become ready." >&2; exit 1; }
  sleep 3
done

if [[ "$(env_value GARDEN_AUTH_ENABLED)" == "1" ]]; then
  echo "[notes] GARDEN_AUTH_ENABLED=1: run scripts/plane-garden/deploy.sh's finalize step before go-live."
fi

compose exec -T proxy curl -fsS http://127.0.0.1/healthz >/dev/null
compose ps
echo "[notes] Deployment is healthy."
