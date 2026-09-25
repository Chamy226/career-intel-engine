# n8n on VPS (Docker) — career-intel keeps port 8000

## Architecture
- `career-intel` systemd → `:8000` (unchanged)
- `n8n` Docker → host `:5678`
- Public HTTPS → Cloudflare Tunnel → `localhost:5678` (recommended)

## Security warnings
- Treat `.env`, Telegram bot token, `API_KEY`, and `N8N_ENCRYPTION_KEY` as secrets.
- Do **not** commit `.env` or paste tokens into GitHub/chat.
- Exposing n8n publicly means anyone who finds the URL can try to log in — use a strong owner password and ideally Cloudflare Access.
- Telegram webhook URL will be public HTTPS; that is expected. Keep the bot token private.

## Prefer Cloudflare Tunnel over ngrok for 24/7
| | Cloudflare Tunnel | ngrok free |
|--|--|--|
| Stable hostname | Yes (your domain / trycloudflare) | Changes unless paid |
| Always-on free | Yes | Sessions / limits |
| Extra process | `cloudflared` | `ngrok` |

---

## 1) VPS: install Docker

```bash
# Replace YOUR_VPS_IP and YOUR_SSH_KEY with your values
env SSH_AUTH_SOCK=0 ssh -i ~/.ssh/YOUR_SSH_KEY -o IdentitiesOnly=yes root@YOUR_VPS_IP
```

On the VPS:

```bash
curl -fsSL https://raw.githubusercontent.com/docker/docker-install/master/install.sh | sh
# OR use the repo script after sync:
# bash /root/n8n/01-install-docker-ubuntu.sh

systemctl enable --now docker
docker --version
docker compose version

# Confirm career-intel still owns 8000 only
ss -lntp | egrep ':8000|:5678' || true
systemctl is-active career-intel
```

---

## 2) Mac: sync files

```bash
chmod +x ~/Desktop/career-intel-engine/deploy/n8n/*.sh
bash ~/Desktop/career-intel-engine/deploy/n8n/02-sync-from-mac.sh
```

Print your local encryption key (needed in VPS `.env`):

```bash
python3 -c "import json; print(json.load(open('$HOME/.n8n/config'))['encryptionKey'])"
```

---

## 3) VPS: create `.env`

```bash
cd /root/n8n
cp .env.example .env
nano .env
```

Set at minimum:
- `N8N_ENCRYPTION_KEY` = Mac encryption key (required to decrypt migrated credentials)
- `N8N_WEBHOOK_URL` / `N8N_EDITOR_BASE_URL` = your final HTTPS URL (set after tunnel exists)
- `CAREER_INTEL_*` for reference when editing HTTP nodes

**HTTP to FastAPI from inside Docker:**  
`http://host.docker.internal:8000` is not always available on Linux. Prefer:

```bash
# on VPS, allow container → host gateway
# In docker-compose, add under n8n service if needed:
#   extra_hosts:
#     - "host.docker.internal:host-gateway"
```

Then point Workflow A/B HTTP nodes to:
`http://host.docker.internal:8000/process-job` and `/update-job-status`.

---

## 4) Tunnel (recommended): Cloudflare

### A. Create tunnel (browser, once)
1. [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) → **Networks** → **Tunnels** → **Create**
2. Name: `n8n-vps`
3. Install connector → choose **Docker** → copy `TUNNEL_TOKEN=eyJ...`
4. Public hostname: `n8n.yourdomain.com` → service `http://n8n:5678`  
   (If cloudflared runs on host network instead, use `http://127.0.0.1:5678`)

### B. Put token in `.env` and start both

```bash
cd /root/n8n
# paste TUNNEL_TOKEN=... into .env
# set:
# N8N_HOST=n8n.yourdomain.com
# N8N_WEBHOOK_URL=https://n8n.yourdomain.com/
# N8N_EDITOR_BASE_URL=https://n8n.yourdomain.com/

bash ./03-restore-and-start.sh
docker compose --profile cloudflare up -d
docker compose --profile cloudflare ps
docker compose logs -f n8n
```

If you run cloudflared on the host instead of Compose:

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cloudflared.deb
dpkg -i /tmp/cloudflared.deb
cloudflared service install "$TUNNEL_TOKEN"
systemctl enable --now cloudflared
systemctl status cloudflared --no-pager
```

---

## 4b) Alternative: ngrok on VPS (simpler, less ideal for 24/7 free)

```bash
# On VPS
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc | tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | tee /etc/apt/sources.list.d/ngrok.list
apt-get update && apt-get install -y ngrok

ngrok config add-authtoken YOUR_NGROK_TOKEN   # from https://dashboard.ngrok.com/get-started/your-authtoken

# systemd unit (persistent)
cat >/etc/systemd/system/ngrok-n8n.service <<'EOF'
[Unit]
Description=ngrok tunnel for n8n
After=network.target docker.service

[Service]
ExecStart=/usr/local/bin/ngrok http 5678 --log=stdout
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# If ngrok binary path differs:
which ngrok
# update ExecStart path accordingly

systemctl daemon-reload
systemctl enable --now ngrok-n8n
journalctl -u ngrok-n8n -n 50 --no-pager
```

Then set `N8N_WEBHOOK_URL` to the printed `https://….ngrok-free.app/` and `docker compose restart n8n`.

---

## 5) Re-register Telegram webhook

1. Open `https://YOUR-N8N-HOST/` (login with your existing n8n owner account)
2. Open **Workflow B: Telegram Command Handler**
3. Confirm Telegram credential still works (same encryption key → migrated)
4. **Deactivate** → wait 2s → **Activate**
5. Verify:

```bash
# on Mac or VPS
TG_TOKEN='YOUR_BOT_TOKEN'
curl -sS "https://api.telegram.org/bot${TG_TOKEN}/getWebhookInfo" | python3 -m json.tool
```

`url` must contain your Cloudflare/ngrok hostname.

Phone test: `/applied1`

---

## 6) Point workflows at VPS FastAPI

In both workflows’ HTTP Request nodes, set base URL to reach host FastAPI, e.g.:

- `http://host.docker.internal:8000/process-job`
- `http://host.docker.internal:8000/update-job-status`  
  Header: `x-api-key: <full API_KEY from career-intel .env>`

Quick host check from VPS:

```bash
curl -sS http://127.0.0.1:8000/health
docker compose -f /root/n8n/docker-compose.yml exec n8n wget -qO- http://host.docker.internal:8000/health || true
```

If `host.docker.internal` fails, add to `docker-compose.yml` under `n8n`:

```yaml
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

then `docker compose up -d n8n`.

---

## 7) Verification checklist

```bash
systemctl is-active career-intel
ss -lntp | egrep ':8000|:5678'
cd /root/n8n && docker compose ps
docker compose logs --tail=100 n8n
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5678/
curl -sS https://YOUR-N8N-HOST/   # via tunnel
```

---

## Rollback
```bash
cd /root/n8n
docker compose --profile cloudflare down
# career-intel untouched
systemctl status career-intel --no-pager
```
