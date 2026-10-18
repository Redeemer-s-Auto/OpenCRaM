#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${1:-}"
BACKUP_DIR="${2:-}"
CONFIRM="${3:-}"
COMPOSE_FILE="$ROOT_DIR/plane-community/docker-compose.garden.yml"

[[ -n "$ENV_FILE" && -n "$BACKUP_DIR" ]] || {
  echo "Usage: $0 <.env.garden> <backup-directory> --confirm-destructive" >&2
  exit 2
}
[[ "$CONFIRM" == "--confirm-destructive" ]] || {
  echo "Refusing live restore without --confirm-destructive" >&2
  exit 2
}
[[ -f "$ENV_FILE" ]] || { echo "Environment file not found: $ENV_FILE" >&2; exit 1; }
[[ -d "$BACKUP_DIR" ]] || { echo "Backup directory not found: $BACKUP_DIR" >&2; exit 1; }

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

(
  cd "$BACKUP_DIR"
  sha256sum -c SHA256SUMS
)

# Prove the backup can restore before touching production state.
bash "$ROOT_DIR/scripts/plane-garden/verify-restore.sh" "$BACKUP_DIR"

echo "[garden-work restore] Stopping Garden Work application and state services..."
compose down

echo "[garden-work restore] Starting empty PostgreSQL service against the persistent volume..."
compose up -d plane-db
ready=0
for _ in $(seq 1 30); do
  if compose exec -T plane-db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
[[ "$ready" == "1" ]] || { echo "PostgreSQL did not become ready" >&2; exit 1; }

echo "[garden-work restore] Recreating production database..."
compose exec -T plane-db sh -c '
  dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"
  createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
'
compose exec -T plane-db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges' < "$BACKUP_DIR/postgres.dump"

echo "[garden-work restore] Restoring object-storage volume..."
docker run --rm -v garden_work_uploads:/restore postgres:15.7-alpine sh -c 'find /restore -mindepth 1 -delete'
docker run --rm \
  -v garden_work_uploads:/restore \
  -v "$BACKUP_DIR:/backup:ro" \
  postgres:15.7-alpine \
  sh -c 'cd /restore && tar -xzf /backup/uploads.tar.gz'

echo "[garden-work restore] Re-deploying current vendored application code against restored state..."
bash "$ROOT_DIR/scripts/plane-garden/deploy.sh" "$ENV_FILE"

echo "[garden-work restore] Restore completed and deployment health checks passed."
