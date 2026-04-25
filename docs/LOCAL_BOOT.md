# Local bootstrap and one-command boot

## Fresh install from zero

Backend uses pinned constraints:

```bash
./scripts/bootstrap_local.sh
```

This creates `.venv`, installs backend requirements with `backend/constraints.txt`, and installs mobile dependencies with npm when Node is available.

## One-command backend boot

```bash
./scripts/local_boot.sh
```

Environment overrides:

- `VICTOR_CONFIG` - backend config path
- `VICTOR_HOST` - bind host
- `VICTOR_PORT` - bind port

## Verification

```bash
make verify-backend
make verify-mobile
```
