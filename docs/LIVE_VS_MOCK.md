# Live vs mock mode

The mobile app now treats live/backend and demo/mock posture as distinct states.

## Modes

- `LIVE BACKEND MODE` - command center snapshot plus engine state resolved from the backend
- `BACKEND CONNECTED · DEMO DATA` - backend reachable, but fallback/demo-style state is being shown for missing live fields
- `MOCK / DEMO MODE` - deterministic demo seed only; no live backend control should be assumed

## Operator guidance

- Never assume demo mode reflects executable capital state.
- Use backend mode for governance, engine visibility, and real telemetry.
- Keep read-only/demo posture for onboarding and UI walkthroughs.
