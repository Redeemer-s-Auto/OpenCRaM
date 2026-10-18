#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/plane-community/.env.garden}"
COMPOSE_FILE="$ROOT_DIR/plane-community/docker-compose.garden.yml"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down
