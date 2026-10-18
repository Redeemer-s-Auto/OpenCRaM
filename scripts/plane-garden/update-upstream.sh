#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PLANE_DIR="$ROOT/plane-community"
UPSTREAM_FILE="$PLANE_DIR/.garden-upstream"
STAGE_DIR="${TMPDIR:-/tmp}/garden-plane-upstream"

if [[ ! -f "$UPSTREAM_FILE" ]]; then
  echo "Missing $UPSTREAM_FILE" >&2
  exit 1
fi

UPSTREAM="$(awk -F= '$1=="upstream" {print substr($0,index($0,"=")+1)}' "$UPSTREAM_FILE")"
CURRENT_REF="$(awk -F= '$1=="ref" {print substr($0,index($0,"=")+1)}' "$UPSTREAM_FILE")"
TARGET_REF="${1:-$CURRENT_REF}"

if [[ -z "$UPSTREAM" || -z "$TARGET_REF" ]]; then
  echo "Unable to resolve Plane upstream/ref from $UPSTREAM_FILE" >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is required" >&2
  exit 1
fi

rm -rf "$STAGE_DIR"
echo "Staging Plane upstream $TARGET_REF from $UPSTREAM"
git clone --depth 1 --branch "$TARGET_REF" "$UPSTREAM" "$STAGE_DIR"
rm -rf "$STAGE_DIR/.git"

cat <<EOF

Upstream has been staged at:
  $STAGE_DIR

Current Garden fork remains untouched at:
  $PLANE_DIR

Next steps:
  1. Compare the staged upstream tree with plane-community/.
  2. Review upstream security/migration changes.
  3. Reconcile Garden changes listed in plane-community/GARDEN_CHANGES.md.
  4. Build/test the staged merge locally.
  5. Only after review, copy selected changes into plane-community/ and update .garden-upstream.

This script intentionally never rsyncs, deletes, or overwrites the Garden fork.
EOF
