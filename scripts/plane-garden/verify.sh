#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/plane-community/.env.garden}"
COMPOSE_FILE="$ROOT_DIR/plane-community/docker-compose.garden.yml"

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

env_value() {
  local key="$1"
  awk -v key="$key" '
    $0 !~ /^[[:space:]]*#/ {
      pos = index($0, "=")
      if (pos > 0 && substr($0, 1, pos - 1) == key) {
        value = substr($0, pos + 1)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
        gsub(/^"|"$/, "", value)
        print value
        exit
      }
    }
  ' "$ENV_FILE"
}

bash "$ROOT_DIR/scripts/plane-garden/preflight.sh" "$ENV_FILE"

command -v corepack >/dev/null 2>&1 || { echo "corepack is required for Plane regression checks" >&2; exit 1; }

cd "$ROOT_DIR"
echo "[garden-work verify] Plane typecheck..."
corepack pnpm --dir plane-community check:types

echo "[garden-work verify] Plane lint..."
corepack pnpm --dir plane-community check:lint

echo "[garden-work verify] Building all Garden Plane application images from vendored source..."
compose build api web space live proxy
compose --profile maintenance build admin

api_image="$(env_value GARDEN_PLANE_API_IMAGE)"
[[ -n "$api_image" ]] || api_image="garden-plane-api:local"

suffix="$$-$RANDOM"
network="garden-work-test-$suffix"
pg="garden-work-test-pg-$suffix"
redis="garden-work-test-redis-$suffix"

cleanup() {
  docker rm -f "$pg" "$redis" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create "$network" >/dev/null
docker run -d --name "$pg" --network "$network" \
  -e POSTGRES_USER=plane_test \
  -e POSTGRES_PASSWORD=plane_test \
  -e POSTGRES_DB=plane_test \
  postgres:15.7-alpine >/dev/null
docker run -d --name "$redis" --network "$network" valkey/valkey:7.2.11-alpine >/dev/null

ready=0
for _ in $(seq 1 30); do
  if docker exec "$pg" pg_isready -U plane_test -d plane_test >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
[[ "$ready" == "1" ]] || { echo "Disposable Plane test database did not become ready" >&2; exit 1; }

echo "[garden-work verify] Garden-specific Plane API tests in disposable infrastructure..."
docker run --rm --network "$network" \
  -e DJANGO_SETTINGS_MODULE=plane.settings.test \
  -e DATABASE_URL="postgresql://plane_test:plane_test@$pg:5432/plane_test" \
  -e REDIS_URL="redis://$redis:6379/0" \
  -e GARDEN_FIREBASE_PROJECT_ID=church-2612f \
  -e GARDEN_AUTH_ENABLED=1 \
  -e GARDEN_AUTH_ALLOWED_ORIGINS=https://garden-test.invalid \
  "$api_image" \
  sh -lc 'pip install -r requirements/test.txt --no-cache-dir >/dev/null && python manage.py check && pytest -q plane/garden/tests'

trap - EXIT
cleanup

echo "[garden-work verify] PASS"
