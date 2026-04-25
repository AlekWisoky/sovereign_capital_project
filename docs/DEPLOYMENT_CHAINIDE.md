# Deploying x∆v backend on ChainIDE (real-time, safe-by-default)

ChainIDE provides a cloud sandbox + **Port Manager** (port forwarding) so your FastAPI backend can be reached from your phone.

This guide assumes you want **real-time scanning + dashboards** first (dry-run), then later you can migrate to a VPS for live execution.

## 0) Recommended mode for ChainIDE

Run the backend in **public deployment mode**:

```bash
export VICTOR_DEPLOYMENT_MODE=public
```

Public mode:
- forces `dry_run=true`
- forces `withdraw_mode=txdata` (WalletConnect signs)
- disables tx-broadcasting endpoints by default

This is ideal for port-forwarded sandbox URLs.

## 1) Create a ChainIDE project

1) Create/import your project in ChainIDE.
2) Open a **Sandbox** (terminal-enabled environment).

## 2) Backend runtime sandbox (FastAPI scanner/executor)

In the sandbox terminal:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Set environment variables:

```bash
export VICTOR_CONFIG=./config/ethereum.yaml
export VICTOR_ADMIN_KEY='change-me-long-random'
export VICTOR_AUTOSTART=1
export VICTOR_DEPLOYMENT_MODE=public
```

Start the API server (bind to 0.0.0.0 so the sandbox can forward it):

```bash
uvicorn victor_ai_bot.server:app --host 0.0.0.0 --port 8000
```

## 3) Expose port 8000 using ChainIDE Port Manager

ChainIDE’s official port-forward workflow is:

1) Run the sandbox
2) Open **Port Manager**
3) Click **Add Port**, enter the port (8000), and click **Add**
4) Click the **jump** button to open the forwarded URL

(See: ChainIDE “Port Forwarding” guide.)

Once forwarded, ChainIDE will give you an **HTTPS URL** for the port.

Because it is HTTPS, mobile will use **WSS** automatically for WebSockets.

If you later move to a VPS, use `docs/DEPLOYMENT_VPS_CADDY.md` to put Caddy in front.

## 4) Connect the mobile app

In the mobile app Setup:

- Backend URL: paste the **HTTPS** forwarded URL from ChainIDE Port Manager
- Admin Key: paste the same `VICTOR_ADMIN_KEY`

The app will automatically use **WSS** for WebSockets when your base URL is HTTPS.

## 5) Multi-sandbox layout (recommended)

Use separate sandboxes to reduce blast radius:

### A) Backend runtime sandbox
- Runs FastAPI scanner/executor
- Stores ONLY non-sensitive config by default
- Use `VICTOR_DEPLOYMENT_MODE=public`

### B) Contracts sandbox
- Foundry deploy/verify
- No backend secrets

### C) Simulation sandbox
- Forked testing / replay logs / strategy tuning
- Safe place to profile RPC latency and quote behavior

## 6) Key security notes for ChainIDE

- Treat port-forwarded URLs as potentially public.
- Always set `VICTOR_ADMIN_KEY`.
- Prefer **public deployment mode** on ChainIDE.
- Do not place production private keys in a shared sandbox.
