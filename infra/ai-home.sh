#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Bind-mounted mode-600 credentials must be readable by the non-root consumer UID.
export AI_CONSUMER_UID="${AI_CONSUMER_UID:-$(id -u)}"
export AI_CONSUMER_GID="${AI_CONSUMER_GID:-$(id -g)}"
if [[ "$AI_CONSUMER_UID" == 0 || "$AI_CONSUMER_GID" == 0 ]]; then
  echo "Run as the non-root owner of .secrets/ai, or set AI_CONSUMER_UID/GID." >&2
  exit 1
fi

compose=(docker compose --env-file .env.home
  -f docker-compose.yml -f docker-compose.home.yml
  -f docker-compose.ai.yml -f docker-compose.retrieval.yml
  -f docker-compose.ai-runtime.yml --profile ai --profile embeddings)

if [[ "${1:-}" == backup ]]; then
  umask 077
  mkdir -p backups
  "${compose[@]}" up --detach --wait postgres
  target=$(mktemp "backups/before-ai-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX.dump")
  if ! "${compose[@]}" exec -T postgres sh -c \
    'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$target"; then
    rm -f "$target"
    exit 1
  fi
  echo "Database backup: $target"
elif (( $# == 0 )); then
  "${compose[@]}" config --quiet
else
  "${compose[@]}" "$@"
fi
