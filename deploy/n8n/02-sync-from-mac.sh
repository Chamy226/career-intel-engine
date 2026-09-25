#!/usr/bin/env bash
# Run on your Mac. Syncs n8n data + this deploy pack to the VPS.
set -euo pipefail

VPS="${VPS:-root@YOUR_VPS_IP}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/YOUR_SSH_KEY}"
SSH=(env SSH_AUTH_SOCK=0 ssh -i "$SSH_KEY" -o IdentitiesOnly=yes)
RSYNC_SSH="env SSH_AUTH_SOCK=0 ssh -i $SSH_KEY -o IdentitiesOnly=yes"
REMOTE_DIR="${REMOTE_DIR:-/root/n8n}"

echo "==> Creating remote dirs"
"${SSH[@]}" "$VPS" "mkdir -p '$REMOTE_DIR' '$REMOTE_DIR/import' '$REMOTE_DIR/backup-from-mac'"

echo "==> Syncing docker-compose pack"
rsync -avz -e "$RSYNC_SSH" \
  --exclude '.env' \
  "$HOME/Desktop/career-intel-engine/deploy/n8n/" \
  "$VPS:$REMOTE_DIR/"

echo "==> Syncing workflow JSON exports (safe fallback import)"
rsync -avz -e "$RSYNC_SSH" \
  "$HOME/Desktop/career-intel-engine/n8n-workflows/" \
  "$VPS:$REMOTE_DIR/import/"

echo "==> Syncing local n8n DB + config (credentials decrypt ONLY if N8N_ENCRYPTION_KEY matches)"
# Stop local n8n first if it is writing to the DB (recommended).
rsync -avz -e "$RSYNC_SSH" \
  "$HOME/.n8n/database.sqlite" \
  "$HOME/.n8n/config" \
  "$VPS:$REMOTE_DIR/backup-from-mac/"

echo "✅ Sync complete → $VPS:$REMOTE_DIR"
echo "Next on VPS: create $REMOTE_DIR/.env from .env.example, then restore + start (see README)."
