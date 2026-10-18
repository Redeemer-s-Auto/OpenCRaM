#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${1:-}"
[[ -n "$BACKUP_DIR" ]] || { echo "Usage: $0 <backup-directory>" >&2; exit 2; }
[[ -d "$BACKUP_DIR" ]] || { echo "Backup directory not found: $BACKUP_DIR" >&2; exit 1; }
[[ -f "$BACKUP_DIR/postgres.dump" ]] || { echo "Missing postgres.dump" >&2; exit 1; }
[[ -f "$BACKUP_DIR/uploads.tar.gz" ]] || { echo "Missing uploads.tar.gz" >&2; exit 1; }
[[ -f "$BACKUP_DIR/SHA256SUMS" ]] || { echo "Missing SHA256SUMS" >&2; exit 1; }

(
  cd "$BACKUP_DIR"
  sha256sum -c SHA256SUMS
)

suffix="$$-$RANDOM"
pg_container="garden-work-restore-pg-$suffix"
upload_volume="garden_work_restore_uploads_$suffix"

cleanup() {
  docker rm -f "$pg_container" >/dev/null 2>&1 || true
  docker volume rm "$upload_volume" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[garden-work restore-test] Creating disposable PostgreSQL..."
docker run -d --name "$pg_container" \
  -e POSTGRES_USER=restore \
  -e POSTGRES_PASSWORD=restore-only-local \
  -e POSTGRES_DB=restore \
  postgres:15.7-alpine >/dev/null

ready=0
for _ in $(seq 1 30); do
  if docker exec "$pg_container" pg_isready -U restore -d restore >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
[[ "$ready" == "1" ]] || { echo "Disposable PostgreSQL did not become ready" >&2; exit 1; }

echo "[garden-work restore-test] Restoring PostgreSQL dump..."
docker exec -i "$pg_container" pg_restore \
  -U restore -d restore --no-owner --no-privileges < "$BACKUP_DIR/postgres.dump"

table_count="$(docker exec "$pg_container" psql -U restore -d restore -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")"
[[ "$table_count" =~ ^[0-9]+$ ]] || { echo "Unable to count restored tables" >&2; exit 1; }
(( table_count > 0 )) || { echo "Restored database contains no public tables" >&2; exit 1; }

echo "[garden-work restore-test] Restoring object-storage archive into a disposable volume..."
docker volume create "$upload_volume" >/dev/null
docker run --rm \
  -v "$upload_volume:/restore" \
  -v "$BACKUP_DIR:/backup:ro" \
  postgres:15.7-alpine \
  sh -c 'cd /restore && tar -xzf /backup/uploads.tar.gz'

object_count="$(docker run --rm -v "$upload_volume:/restore:ro" postgres:15.7-alpine sh -c 'find /restore -type f | wc -l')"
[[ "$object_count" =~ ^[0-9]+$ ]] || { echo "Unable to count restored object-store files" >&2; exit 1; }

echo "[garden-work restore-test] PASS"
echo "  restored_tables=$table_count"
echo "  restored_object_files=$object_count"
