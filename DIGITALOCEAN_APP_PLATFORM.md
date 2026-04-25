# DigitalOcean App Platform backend deployment

The repo root contains a deploy-detectable `Dockerfile`, `Procfile`, and requirements shims so App Platform can detect the backend from `/` without guessing a subdirectory.

Canonical runtime data path:
- `/app/backend/data`

Backward-compatible startup migration:
- if an older image or archive still contains legacy nested runtime residue under `/app/backend/backend/data`, the startup script copies missing files into `/app/backend/data` before boot.

Recommended settings:
- Source Directory: `/`
- HTTP Port: `8000`
- Build Command: Dockerfile autodetect
- Run Command: Dockerfile / Procfile autodetect

Required env vars:
- `VICTOR_CONFIG=/app/backend/config/ethereum.yaml`
- `VICTOR_ADMIN_KEY=...`
- `VICTOR_CORS_ALLOW_ORIGINS=https://your-mobile-web-origin`
- `PORT=8000`


## Canonical runtime data root

The backend now treats `backend/data` as the canonical runtime data root. Legacy top-level `data/` is only used as a migration source when present.
