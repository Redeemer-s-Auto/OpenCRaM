#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/plane-community/.env.garden}"
COMPOSE_FILE="$ROOT_DIR/plane-community/docker-compose.garden.yml"

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

compose ps

echo ""
echo "[garden-work] API readiness"
compose exec -T api python -c "import json, urllib.request; print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:8000/auth/firebase/health/', timeout=3)), indent=2))"

echo ""
echo "[garden-work] Object storage"
compose exec -T proxy curl -fsS http://plane-minio:9000/minio/health/live >/dev/null
echo "ok"
