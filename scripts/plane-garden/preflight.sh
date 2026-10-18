#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/plane-community/.env.garden}"
COMPOSE_FILE="$ROOT_DIR/plane-community/docker-compose.garden.yml"

fail() {
  echo "[garden-work preflight] ERROR: $*" >&2
  exit 1
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

[[ -f "$ENV_FILE" ]] || fail "Missing environment file: $ENV_FILE"
[[ -f "$COMPOSE_FILE" ]] || fail "Missing compose file: $COMPOSE_FILE"
command -v docker >/dev/null 2>&1 || fail "docker is required"
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required"

required_keys=(
  GARDEN_WORK_URL GARDEN_ADMIN_URL SITE_ADDRESS ALLOWED_HOSTS CORS_ALLOWED_ORIGINS
  GARDEN_AUTH_ALLOWED_ORIGINS GARDEN_FIREBASE_PROJECT_ID GARDEN_FIREBASE_CREDENTIALS_PATH
  SECRET_KEY LIVE_SERVER_SECRET_KEY POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB
  RABBITMQ_USER RABBITMQ_PASSWORD RABBITMQ_VHOST AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
  MINIO_IMAGE
)

for key in "${required_keys[@]}"; do
  [[ -n "$(env_value "$key")" ]] || fail "$key must be set in $ENV_FILE"
done

work_url="$(env_value GARDEN_WORK_URL)"
admin_url="$(env_value GARDEN_ADMIN_URL)"
allowed_hosts="$(env_value ALLOWED_HOSTS)"
cors_origins="$(env_value CORS_ALLOWED_ORIGINS)"
credential_path="$(env_value GARDEN_FIREBASE_CREDENTIALS_PATH)"

[[ "$work_url" == https://* ]] || fail "GARDEN_WORK_URL must use HTTPS"
[[ "$admin_url" == https://* ]] || fail "GARDEN_ADMIN_URL must use HTTPS"
[[ "$allowed_hosts" != *"*"* ]] || fail "ALLOWED_HOSTS cannot contain a wildcard"
[[ "$cors_origins" != *"*"* ]] || fail "CORS_ALLOWED_ORIGINS cannot contain a wildcard"
[[ -f "$credential_path" ]] || fail "Firebase credential file not found: $credential_path"

if grep -q 'makeplane/plane-' "$COMPOSE_FILE"; then
  fail "Garden compose must build application images from vendored source, not makeplane/plane-* images"
fi

if grep -Eq '^[[:space:]]+(plane-db|plane-redis|plane-mq|plane-minio):$' "$COMPOSE_FILE"; then
  : # expected internal services exist
else
  fail "Garden compose is missing one or more internal infrastructure services"
fi

(
  cd "$ROOT_DIR"
  node scripts/plane-garden/verify-boundary.mjs
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config >/dev/null
)

echo "[garden-work preflight] OK"
