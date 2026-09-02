# Render staging verification

Render is the runtime/staging verification layer after Linux CI. It is not the production execution authority.

## Safety contract

The repository's Ethereum configuration currently has `execution.dry_run: true` and `execution.auto_trading: false`. Render staging must preserve that posture. The staging verifier also fails if `/api/state` exposes `auto_trading: true` anywhere in its read model.

OMAR may be enabled in staging because its current implementation is a learning/self-play overlay and does not submit real trades. Real execution remains governed by the canonical decision → governance → execution → settled-outcome lifecycle.

## Existing Render blueprint

`render.yaml` already defines the Render web service, Docker runtime, `/health` health check, public deployment defaults, disabled public broadcast, and the OMAR feature flag. Keep staging credentials separate from production credentials.

Do not place private keys or administrator secrets in the repository. Render should supply them as secret environment variables when a staging workflow genuinely requires them.

## Manual verification

After Render deploys the staging service:

```bash
export RENDER_STAGING_URL='https://<your-render-service>.onrender.com'
python scripts/verify_render_staging.py
```

The verifier performs read-only checks against:

- `/health`
- `/api/deploy/info`
- `/api/state`

It does not call execution commands, authenticate as an operator, submit transactions, or enable auto trading.

## GitHub Actions

The `Production Runtime Gate` workflow first runs the Linux production-runtime integration test and the execution-learning launch contracts, followed by the complete backend regression suite. If the repository secret `RENDER_STAGING_URL` is configured, the same workflow then performs the Render staging smoke check on pushes/manual runs.

This gives us two distinct gates:

1. **Linux CI:** deterministic proof that the real runtime method chain, identity propagation, execution boundary, outcome/learning contracts, and backend tests remain coherent.
2. **Render staging:** proof that the deployed web runtime boots and exposes the expected read surface while retaining a non-executing staging posture.

Neither gate is a substitute for governance, contract audit, wallet/key controls, or a controlled production capital rollout.
