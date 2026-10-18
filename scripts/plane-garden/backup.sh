#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/plane-community/.env.garden}"
BACKUP_ROOT="${2:-/var/backups/garden-work}"
COMPOSE_FILE="$ROOT_DIR/plane-community/docker-compose.garden.yml"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$BACKUP_ROOT/$TIMESTAMP"

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

running_services="$(compose ps --services --filter status=running || true)"
to_restart=()
for service in proxy web space live worker beat-worker api; do
  if grep -qx "$service" <<<"$running_services"; then
    to_restart+=("$service")
  fi
done

restart_apps() {
  if ((${#to_restart[@]})); then
    compose up -d "${to_restart[@]}" >/dev/null || true
  fi
}
trap restart_apps EXIT

if ((${#to_restart[@]})); then
  echo "[garden-work backup] Pausing write-capable application services for a consistent snapshot..."
  compose stop "${to_restart[@]}"
fi

echo "[garden-work backup] Dumping PostgreSQL..."
compose exec -T plane-db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$BACKUP_DIR/postgres.dump"

echo "[garden-work backup] Archiving object storage volume..."
docker run --rm \
  -v garden_work_uploads:/source:ro \
  -v "$BACKUP_DIR:/backup" \
  postgres:15.7-alpine \
  sh -c 'cd /source && tar -czf /backup/uploads.tar.gz .'

{
  echo "created_utc=$TIMESTAMP"
  echo "repository=yadasa/church"
  echo "commit=$(git -C "$ROOT_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "plane_upstream=$(cat "$ROOT_DIR/plane-community/.garden-upstream" 2>/dev/null | tr '\n' ' ' || true)"
  echo "postgres_image=postgres:15.7-alpine"
  echo "uploads_volume=garden_work_uploads"
  echo "note=Secrets and .env.garden are intentionally not included."
} > "$BACKUP_DIR/manifest.txt"

(
  cd "$BACKUP_DIR"
  sha256sum postgres.dump uploads.tar.gz manifest.txt > SHA256SUMS
)

trap - EXIT
restart_apps

echo "[garden-work backup] Backup written to $BACKUP_DIR"
echo "[garden-work backup] Run: bash scripts/plane-garden/verify-restore.sh '$BACKUP_DIR'"
