
# Backend deployment detection for GitHub -> DigitalOcean

The repo root now contains a deploy-detectable Dockerfile, requirements shims, Procfile, and environment example so DigitalOcean App Platform can identify the backend from the repository root.

## Detection-safe files at repo root
- `Dockerfile`
- `requirements.txt`
- `requirements-dev.txt`
- `Procfile`
- `.env.example`

## Hosted backend command
The Dockerfile and Procfile both route to `backend/scripts/start-server.sh`, which honors `PORT` and creates required runtime directories before boot.
