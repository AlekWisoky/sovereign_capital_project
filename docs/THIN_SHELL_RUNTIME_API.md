# Thin-shell runtime and API

`backend/victor_ai_bot/runtime.py` and `backend/victor_ai_bot/api.py` are now compatibility shells.

Operational truth:
- runtime construction and lifespan wiring live in `victor_ai_bot/runtime_core/`
- the legacy runtime body lives in `victor_ai_bot/runtime_legacy.py`
- the legacy API router lives in `victor_ai_bot/api_legacy.py`
- public imports remain stable for `RuntimeBundle`, `MultiRuntimeBundle`, and `router`

Guardrail:
- keep public shells thin
- move new orchestration into `runtime_core`, `runtime_services`, `api_routes`, and `api_facades`
