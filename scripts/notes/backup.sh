#!/usr/bin/env bash
# Nightly Notes backup: PostgreSQL dump + uploads volume, checksummed, kept KEEP_DAYS days.
# Same capture as scripts/plane-garden/backup.sh, but it uses both compose files and
# `stop`/`start` (never `up`), so the backup can never recreate containers with a
# different config than the live deploy.
# Usage: bash scripts/notes/backup.sh /opt/notes/.env.notes [/var/backups/notes] [KEEP_DAYS]
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$(realpath -m "${1:?Usage: backup.sh <env file> [backup root] [keep days]}")"
BACKUP_ROOT="${2:-/var/backups/notes}"
KEEP_DAYS="${3:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DIR="$BACKUP_ROOT/$STAMP"
cd "$ROOT_DIR/plane-community"

compose() {
  docker compose --env-file "$ENV_FILE" -f docker-compose.garden.yml -f docker-compose.notes.yml "$@"
}

mkdir -p "$BACKUP_ROOT" && chmod 700 "$BACKUP_ROOT"
mkdir -m 700 "$DIR.partial"

running="$(compose ps --services --filter status=running || true)"
paused=()
for svc in proxy web space live worker beat-worker api; do
  grep -qx "$svc" <<<"$running" && paused+=("$svc")
done
resume() { ((${#paused[@]})) && compose start "${paused[@]}" >/dev/null || true; }
trap resume EXIT

((${#paused[@]})) && compose stop "${paused[@]}" >/dev/null
echo "[notes backup] $(date +%T) app paused; dumping PostgreSQL"
compose exec -T plane-db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' >"$DIR.partial/postgres.dump"
echo "[notes backup] $(date +%T) archiving uploads"
docker run --rm -v garden_work_uploads:/source:ro -v "$DIR.partial:/backup" postgres:15.7-alpine \
  sh -c 'cd /source && tar -czf /backup/uploads.tar.gz .'
trap - EXIT
resume
echo "[notes backup] $(date +%T) app resumed"

{
  echo "created_utc=$STAMP"
  echo "commit=$(git -C "$ROOT_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "postgres_image=postgres:15.7-alpine"
  echo "uploads_volume=garden_work_uploads"
  echo "note=Secrets and the env file are not included."
} >"$DIR.partial/manifest.txt"
(cd "$DIR.partial" && sha256sum postgres.dump uploads.tar.gz manifest.txt >SHA256SUMS)
# A finished backup has no ".partial" suffix; copy jobs only take finished ones.
mv "$DIR.partial" "$DIR"

find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name '20*' -mtime +"$KEEP_DAYS" -exec rm -rf {} +
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name '*.partial' -mtime +1 -exec rm -rf {} +
echo "[notes backup] $(date +%T) done: $DIR ($(du -sh "$DIR" | cut -f1))"
