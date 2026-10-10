# VPS deployment (HTTPS + WSS with Caddy)

This is the recommended path for stable production hosting.

## 1) Host layout

Use:

```text
/opt/sovereign_capital/
  repo/
  env/
    backend.env
    caddy.env
  backend-data/
  backups/
  logs/
```

The runtime data directory is deliberately outside the Git working tree. The Compose bind mount maps `/opt/sovereign_capital/backend-data` to `/app/backend/data`.

## 2) Environment files

Copy the tracked examples and edit the real files on the server:

```bash
mkdir -p /opt/sovereign_capital/env /opt/sovereign_capital/backend-data
cp /opt/sovereign_capital/repo/env/backend.env.example /opt/sovereign_capital/env/backend.env
cp /opt/sovereign_capital/repo/env/caddy.env.example /opt/sovereign_capital/env/caddy.env
chmod 600 /opt/sovereign_capital/env/backend.env /opt/sovereign_capital/env/caddy.env
```

`backend.env` contains the privileged `VICTOR_ADMIN_KEY` and exact frontend CORS origin. Never commit the real files.

## 3) Backend

The production Compose file binds the backend to `127.0.0.1:8000` and exposes it only through Caddy. Public port 8000 must remain closed.

## 4) Caddy / TLS

Set `API_HOST` in `env/caddy.env` to the real API hostname, for example `api.example.com`. Point the DNS A/AAAA records at the UpCloud server before starting Caddy.

Caddy reads `API_HOST` from the environment and provisions HTTPS for the hostname.

## 5) Firewall

Allow only:

- SSH (22), preferably restricted to trusted administration sources
- HTTP (80)
- HTTPS (443)

Do not publish 8000. The application already binds that port to loopback.

If using both UpCloud L3 firewall and UFW, configure and verify both before enabling restrictive defaults so SSH access is not lost.

## 6) Deployment identity

Stamp the exact checked-out Git SHA into the backend container, then verify the running API reports the same identity before proceeding:

```bash
SHA="$(git rev-parse HEAD)"
test "${#SHA}" -eq 40
VICTOR_GIT_SHA="$SHA" docker compose -f deploy/docker-compose.prod.yml up -d --build --force-recreate victor-backend
docker compose -f deploy/docker-compose.prod.yml ps victor-backend
DEPLOYED_SHA="$(curl -fsS https://YOUR_API_HOST/api/deploy/info | python3 -c 'import json,sys; print(json.load(sys.stdin).get("git_sha", "unknown"))')"
printf 'EXPECTED_SHA=%s\nDEPLOYED_SHA=%s\n' "$SHA" "$DEPLOYED_SHA"
test "$DEPLOYED_SHA" = "$SHA"
```

The `/api/deploy/info` endpoint reports `git_sha` from `VICTOR_GIT_SHA` and reports `unknown` when a build was not stamped. Do not treat `unknown` or a mismatch as a verified deployment.

## 7) Safe mode

Keep the current Ethereum configuration non-live:

- `dry_run=true`
- `auto_trading=false`
- no `VICTOR_PRIVATE_KEY`
- no live signer configuration
- no live-authority activation

Infrastructure readiness does not authorize live trading. Issue #89 remains the explicit live-authority gate.
