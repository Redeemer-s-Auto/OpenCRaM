#!/usr/bin/env bash
# Nightly Notes backup: PostgreSQL dump + uploads volume, checksummed, kept KEEP_DAYS days.
# Same capture as scripts/plane-garden/backup.sh, but it uses both compose files and
# `stop`/`start` (never `up`), so the backup can never recreate containers with a
# different config than the live deploy.
# Usage: bash scripts/notes/backup.sh /opt/notes/.env.notes [/var/backups/notes] [KEEP_DAYS]
#
# Heartbeat: when NOTES_HEARTBEAT_URL is set (in the env file, or in the environment), the script POSTs
# {"kind":"backup","ok":true|false,...} there after a finished backup, and ok:false from the EXIT trap when it
# fails. The shared secret is read at run time from NOTES_HEARTBEAT_SECRET_FILE (default
# /opt/notes/secrets/notes-access-secret.txt) and handed to curl through a mode-600 header file, never on the
# command line. URL unset or secret file missing: no heartbeat, silently. A failed heartbeat never fails the backup.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$(realpath -m "${1:?Usage: backup.sh <env file> [backup root] [keep days]}")"
BACKUP_ROOT="${2:-/var/backups/notes}"
KEEP_DAYS="${3:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DIR="$BACKUP_ROOT/$STAMP"
cd "$ROOT_DIR/plane-community"

env_value() { # the last NAME=value line in the env file, quotes stripped
  local v
  v="$(grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d= -f2- || true)"
  v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"
  printf '%s' "$v"
}
HEARTBEAT_URL="${NOTES_HEARTBEAT_URL:-$(env_value NOTES_HEARTBEAT_URL)}"
HEARTBEAT_SECRET_FILE="${NOTES_HEARTBEAT_SECRET_FILE:-/opt/notes/secrets/notes-access-secret.txt}"

json_text() { # one line, JSON-escaped, at most 400 characters
  printf '%s' "$1" | tr '\r\n\t' '   ' | tr -d '\000-\037' | cut -c1-400 | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

heartbeat() { # heartbeat <true|false> <stamp> <size> <detail>
  [[ -n "$HEARTBEAT_URL" && -r "$HEARTBEAT_SECRET_FILE" ]] || return 0
  local hdr rc=0
  hdr="$(mktemp)" || return 0
  chmod 600 "$hdr"
  printf 'X-Notes-Access-Secret: %s\n' "$(tr -d '\r\n' <"$HEARTBEAT_SECRET_FILE")" >"$hdr"
  printf '{"kind":"backup","ok":%s,"stamp":"%s","size":"%s","detail":"%s"}' \
    "$1" "$(json_text "$2")" "$(json_text "$3")" "$(json_text "$4")" |
    curl -fsS -o /dev/null --max-time 20 --retry 3 --retry-all-errors -X POST \
      -H @"$hdr" -H 'Content-Type: application/json' --data-binary @- "$HEARTBEAT_URL" || rc=$?
  rm -f "$hdr"
  if ((rc == 0)); then
    echo "[notes backup] $(date +%T) heartbeat sent (ok=$1)"
  else
    echo "[notes backup] $(date +%T) heartbeat FAILED (curl exit $rc)"
  fi
  return 0
}

RESUME_ARMED=0
FAIL_LINE=""
on_exit() {
  local rc=$?
  ((RESUME_ARMED)) && resume
  if ((rc != 0)); then
    echo "[notes backup] $(date +%T) FAILED (exit $rc${FAIL_LINE:+, line $FAIL_LINE})"
    heartbeat false "${STAMP:-}" "" "backup.sh failed (exit $rc${FAIL_LINE:+ at line $FAIL_LINE}); see /var/log/notes-backup.log"
  fi
}
trap on_exit EXIT
trap 'FAIL_LINE=$LINENO' ERR
trap 'exit 143' TERM INT HUP

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
# Start the paused services again, and say so when that fails. On 2026-10-24 `compose start` failed here
# ("dependency failed to start: container garden-work-plane-mq-1 is unhealthy"); the old `|| true` hid it,
# the log said "app resumed", and the app stayed down for 5 days. Now: one retry after 60 s, then return 1.
resume() {
  ((${#paused[@]})) || return 0
  local out try
  for try in 1 2; do
    if out="$(compose start "${paused[@]}" 2>&1)"; then
      ((try == 1)) || echo "[notes backup] $(date +%T) start worked on the retry"
      return 0
    fi
    echo "[notes backup] $(date +%T) start FAILED (try $try): $(tail -n 3 <<<"$out" | tr '\n' ' ')"
    ((try == 1)) && sleep "${NOTES_RESUME_RETRY_SECONDS:-60}"
  done
  return 1
}
APP_DOWN=0
RESUME_ARMED=1

((${#paused[@]})) && compose stop "${paused[@]}" >/dev/null
echo "[notes backup] $(date +%T) app paused; dumping PostgreSQL"
compose exec -T plane-db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' >"$DIR.partial/postgres.dump"
echo "[notes backup] $(date +%T) archiving uploads"
docker run --rm -v garden_work_uploads:/source:ro -v "$DIR.partial:/backup" postgres:15.7-alpine \
  sh -c 'cd /source && tar -czf /backup/uploads.tar.gz .'
RESUME_ARMED=0
if resume; then
  echo "[notes backup] $(date +%T) app resumed"
else
  APP_DOWN=1
  echo "[notes backup] $(date +%T) APP NOT RESUMED; finishing the backup, then reporting a failure"
fi

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
SIZE="$(du -sh "$DIR" | cut -f1)"
echo "[notes backup] $(date +%T) done: $DIR ($SIZE)"
if ((APP_DOWN)); then
  # The data is safe in $DIR, but the app is down: report ok:false so the hub emails, and exit non-zero.
  echo "[notes backup] $(date +%T) FAILED: the app did not start again after the backup"
  heartbeat false "$STAMP" "$SIZE" "backup saved in $DIR, but the app did NOT start again (compose start failed); see /var/log/notes-backup.log"
  trap - EXIT
  exit 3
fi
heartbeat true "$STAMP" "$SIZE" "pg_dump + uploads + SHA256SUMS in $DIR"
