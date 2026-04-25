# Degraded-state model

Launch-learning and rollout now use explicit family health states:
- `live`
- `degraded`
- `observe_only`
- `capped_live`
- `disabled`
- `quarantined`

These states are persisted inside the launch profile, surfaced via `/api/launch/state`, and propagated into operator guidance.

Allowed family transitions are enforced by `victor_ai_bot/fund_os/state_transitions.py`.
