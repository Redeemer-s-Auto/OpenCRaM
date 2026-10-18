#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/plane-community/.env.garden}"
if [[ "$ENV_FILE" != /* ]]; then
  ENV_FILE="$(realpath -m "$ENV_FILE")"
fi
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

cd "$ROOT_DIR/plane-community"

echo "[garden-work] Building application images from vendored source..."
compose build api web space live proxy
compose --profile maintenance build admin

echo "[garden-work] Starting persistent infrastructure..."
compose up -d plane-db plane-redis plane-mq plane-minio

# Plane's API entrypoint creates/verifies the S3 bucket, so the object store must
# be accepting requests before API startup. Probe it from the locally built
# Garden proxy image to avoid adding a one-off third-party helper container.
echo "[garden-work] Waiting for object storage..."
object_ready=0
for _ in $(seq 1 40); do
  if compose run --rm --no-deps proxy curl -fsS http://plane-minio:9000/minio/health/live >/dev/null 2>&1; then
    object_ready=1
    break
  fi
  sleep 3
done

if [[ "$object_ready" != "1" ]]; then
  compose ps
  echo "[garden-work] Object storage did not become ready." >&2
  exit 1
fi

echo "[garden-work] Running migrations..."
compose up --abort-on-container-exit --exit-code-from migrator migrator

echo "[garden-work] Starting application services..."
compose up -d --remove-orphans api worker beat-worker live web space proxy

# Verify API readiness from inside the API container. This does not depend on public DNS being live yet.
echo "[garden-work] Waiting for API readiness..."
ready=0
for _ in $(seq 1 40); do
  if compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/auth/firebase/health/', timeout=3).read()" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 3
done

if [[ "$ready" != "1" ]]; then
  compose ps
  echo "[garden-work] API did not become ready." >&2
  exit 1
fi

# Garden owns identity, authorization, and administration. Plane's native
# first-run/god-mode flow must therefore never be exposed to Garden staff.
# Finalize every registered instance after API startup so an existing instance
# cannot keep advertising is_setup_done=false even if its first Firebase session
# was created before the Garden bootstrap repair shipped.
if [[ "$(env_value GARDEN_AUTH_ENABLED)" == "1" ]]; then
  echo "[garden-work] Finalizing Garden-managed Plane instance..."
  compose exec -T api python manage.py shell -c '
from plane.license.models import Instance
from plane.utils.cache import invalidate_cache_directly
qs = Instance.objects.all()
if not qs.exists():
    raise SystemExit("Garden Work has no registered Plane instance")
qs.update(
    is_setup_done=True,
    is_signup_screen_visited=True,
    is_telemetry_enabled=False,
    is_support_required=False,
)
invalidate_cache_directly(path="/api/instances/", user=False)
if qs.filter(is_setup_done=False).exists():
    raise SystemExit("Garden Work instance setup could not be finalized")
print(f"Garden-managed Plane instance finalized ({qs.count()} row(s)); instance cache cleared.")
'
fi

if ! compose exec -T proxy curl -fsS http://plane-minio:9000/minio/health/live >/dev/null; then
  echo "[garden-work] Object storage health check failed." >&2
  exit 1
fi

if ! compose exec -T proxy curl -fsS http://127.0.0.1/healthz >/dev/null; then
  echo "[garden-work] Reverse proxy health check failed." >&2
  exit 1
fi

compose ps

if [[ "$(env_value GARDEN_WORKSPACE_BOOTSTRAP)" == "1" ]]; then
  echo ""
  echo "[garden-work] WARNING: GARDEN_WORKSPACE_BOOTSTRAP=1."
  echo "Disable it after the first approved work.admin login creates the managed workspace."
fi

echo "[garden-work] Deployment is healthy."
