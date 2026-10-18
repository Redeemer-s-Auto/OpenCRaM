#!/usr/bin/env bash
set -euo pipefail

ARCHIVE="${1:-garden-work-images.tar}"
[[ -f "$ARCHIVE" ]] || { echo "Missing image archive: $ARCHIVE" >&2; exit 1; }

docker load -i "$ARCHIVE"
echo "[garden-work] Images loaded from $ARCHIVE"
