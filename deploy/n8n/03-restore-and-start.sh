#!/usr/bin/env bash
# Run on the VPS after .env is filled and Mac backup is synced.
set -euo pipefail

cd "$(dirname "$0")"
test -f .env || { echo "Missing .env — copy .env.example and fill values"; exit 1; }

# Restore SQLite into the Docker volume path via a one-shot helper container
if [[ -f backup-from-mac/database.sqlite ]]; then
  echo "==> Restoring database into docker volume n8n_n8n_data"
  docker compose up -d --no-deps n8n
  sleep 2
  # Copy into the running container's data dir, then restart
  docker compose cp backup-from-mac/database.sqlite n8n:/home/node/.n8n/database.sqlite
  if [[ -f backup-from-mac/config ]]; then
    docker compose cp backup-from-mac/config n8n:/home/node/.n8n/config || true
  fi
  docker compose restart n8n
else
  echo "==> No DB backup found; starting fresh n8n"
  docker compose up -d n8n
fi

docker compose ps
echo "✅ n8n container started on host port 5678"
echo "Open via your tunnel URL, then deactivate/activate Telegram workflows to re-register webhooks."
