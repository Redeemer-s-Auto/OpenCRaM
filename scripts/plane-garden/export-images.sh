#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/plane-community/.env.garden}"
OUTPUT="${2:-$ROOT_DIR/garden-work-images.tar}"

[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE" >&2; exit 1; }

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

images=(
  "$(env_value GARDEN_PLANE_WEB_IMAGE)"
  "$(env_value GARDEN_PLANE_API_IMAGE)"
  "$(env_value GARDEN_PLANE_SPACE_IMAGE)"
  "$(env_value GARDEN_PLANE_ADMIN_IMAGE)"
  "$(env_value GARDEN_PLANE_LIVE_IMAGE)"
  "$(env_value GARDEN_PLANE_PROXY_IMAGE)"
  "postgres:15.7-alpine"
  "valkey/valkey:7.2.11-alpine"
  "rabbitmq:3.13.6-alpine"
  "$(env_value MINIO_IMAGE)"
)

for image in "${images[@]}"; do
  [[ -n "$image" ]] || { echo "One or more image names are blank in $ENV_FILE" >&2; exit 1; }
  docker image inspect "$image" >/dev/null 2>&1 || { echo "Missing local image: $image" >&2; exit 1; }
done

docker save -o "$OUTPUT" "${images[@]}"
echo "[garden-work] Wrote $OUTPUT"
