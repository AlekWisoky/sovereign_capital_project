# Sentry production setup

Sentry is observability only. It must never become a prerequisite for market-data, decision, governance, signing, execution, receipt, settlement, or OMAR learning. If `SENTRY_DSN` is absent, the application runs normally with Sentry disabled.

## 1. Sentry project

Create/select the Python/FastAPI project shown by the Sentry onboarding screen. Do not commit the DSN to Git.

Set these environment variables on the runtime host (and in the deployment secret store):

```bash
SENTRY_DSN=<your-project-dsn>
SENTRY_ENVIRONMENT=production
SENTRY_RELEASE=<git-commit-sha>
SENTRY_TRACES_SAMPLE_RATE=0.05
SENTRY_PROFILES_SAMPLE_RATE=0.01
SENTRY_ENABLE_LOGS=0
```

For staging, use a separate Sentry environment such as `staging`. The release should be the exact deployed commit SHA so Sentry can associate failures with Git history.

## 2. GitHub integration

In Sentry, install/configure the GitHub integration and authorize the repository:

`AlekWisoky/sovereign_capital_project`

The integration provides commit/release correlation, issue/PR linking, and stack-trace-to-source navigation. Sentry's GitHub integration must have access to the repository you want to use.

## 3. Code mapping for this repository

The repository is a Python monorepo with application code under `backend/`.

For the UI shown during code-path mapping, start with:

- **Repo:** `AlekWisoky/sovereign_capital_project`
- **Branch:** `main`
- **Source Code Root:** `backend/`
- **Stack Trace Root:** leave empty unless the actual Sentry stack trace shows an additional prefix that must be stripped

Do not guess a stack root. After the first real Python exception arrives, inspect the frame path in Sentry and adjust the stack root only if the displayed path does not map cleanly to `backend/...` in GitHub.

## 4. What the application sends

The application intentionally keeps Sentry context limited to safe operational identity and excludes secrets and capital balances. The supported lifecycle tags are:

- `decision_id`
- `correlation_id`
- `execution_id`
- `outcome_id`
- `opportunity_id`
- `route_id`
- `sizing_id`
- `action`
- `mode`

Do not add private keys, seed phrases, signing material, raw authorization headers, or wallet secrets to Sentry events.

## 5. Verify the installation

From the deployed environment, first verify the SDK can initialize without exposing the DSN:

```bash
python -c 'from victor_ai_bot.sentry_config import sentry_settings; print(sentry_settings())'
```

Then trigger a controlled application error in a non-trading/staging environment. Confirm the event appears in Sentry with the expected `environment` and `release`.

Only after that should production error/trace sampling be enabled.

## 6. Trading-system rule

Sentry is not part of the authorization chain. An unavailable Sentry endpoint, SDK failure, or telemetry outage must not block a valid governed trade. The canonical production chain remains:

`market data -> strategy/signal -> OMAR decision -> governance/risk -> execution -> receipt/fill -> settled ledger -> learning`

Sentry observes that chain; it does not authorize it.
