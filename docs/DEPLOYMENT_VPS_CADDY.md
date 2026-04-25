# VPS deployment (HTTPS + WSS with Caddy)

This is the recommended path for stable production hosting.

## 1) Run backend bound to localhost

On the VPS:

```bash
export VICTOR_CONFIG=/opt/vdex/backend/config/ethereum.yaml
export VICTOR_ADMIN_KEY='change-me-long-random'
export VICTOR_AUTOSTART=1
export VICTOR_DEPLOYMENT_MODE=private

uvicorn victor_ai_bot.server:app --host 127.0.0.1 --port 8000
```

## 2) Put Caddy in front (TLS termination)

Create a `Caddyfile`:

```caddy
api.yourdomain.com {
  reverse_proxy 127.0.0.1:8000
}
```

Then run Caddy (systemd or container). With a real hostname, Caddy will automatically provision HTTPS.

This repo includes a production compose template:

- `deploy/docker-compose.prod.yml`
- `deploy/Caddyfile`

## 3) Firewall (open only what you need)

If using UFW:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

Keep port 8000 closed publicly (bind backend to 127.0.0.1).

## 4) Mobile connection

In app Setup:

- Backend URL: `https://api.yourdomain.com`
- Admin Key: matches server

Because the base URL is HTTPS, the app uses **WSS** for WebSockets automatically.
