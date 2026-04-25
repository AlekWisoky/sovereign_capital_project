# Engine subsystems — cross-venue alpha layer

This pass operationalizes five adjacent alpha engines as first-class bounded subsystems inside **x∆v — Sovereign Capital**.

## Added engines

### Cross-CEX + DEX arbitrage
- Module: `backend/victor_ai_bot/aqe/arbitrage/cross_cex_dex_engine.py`
- Emits normalized `cross_cex_dex` opportunities.
- Models DEX depth, venue inventory, transfer friction, settlement delay, and leg risk.
- Intended for inventory-aware spread capture rather than naive spread scanning.

### Funding arbitrage
- Modules:
  - `backend/victor_ai_bot/aqe/funding/carry_model.py`
  - `backend/victor_ai_bot/aqe/funding/risk_model.py`
  - upgraded `backend/victor_ai_bot/aqe/funding/engine.py`
- Emits normalized `funding_arb` opportunities.
- Models carry horizon, funding timing, basis drag, fee drag, collateral efficiency, and liquidation buffer penalties.

### Cross-chain arbitrage
- Modules:
  - `backend/victor_ai_bot/aqe/cross_chain/engine.py`
  - `bridge_model.py`
  - `inventory_model.py`
- Emits conservative `cross_chain_arb` intents only when chain inventory and bridge/finality conditions are acceptable.
- Does **not** assume atomic cross-chain execution.
- Defaults to observe-only or capped-live behavior unless confidence and maturity are sufficient.

### Next-generation MEV search
- Modules:
  - `backend/victor_ai_bot/aqe/mev/search_engine.py`
  - `bundle_builder.py`
  - `simulator.py`
- Preserves the defensive / private-routing-first posture.
- Adds protected/backrun-compatible candidate construction and bundle-quality evaluation.
- Public-send behavior remains blocked by policy for fragile MEV opportunities.

### AI auto strategy generator
- Modules:
  - `backend/victor_ai_bot/aqe/meta/predictor.py`
  - `backend/victor_ai_bot/aqe/meta/family_generation.py`
  - upgraded `backend/victor_ai_bot/aqe/meta/runtime.py`
- Improves family-aware candidate generation, success prediction, and overlap control.
- Generated candidates still enter lifecycle-gated paths (`sandbox`, `paper`, etc.) rather than production by default.

## Engine control layer

To keep these engines from creating shadow workflows, the pass adds:

- `engine_control/capability_registry.py`
- `engine_control/admission_governor.py`
- `engine_control/degradation_policy.py`
- `engine_control/interference.py`
- `engine_control/budgeting.py`

The engine-control layer enforces:
- engine maturity and allowed environments
- lifecycle eligibility
- telemetry/calibration sufficiency
- capital eligibility
- per-engine budgets
- interference and overlap controls
- confidence-to-privilege laddering

## Runtime integration

The runtime integrates the engines through `runtime_services/engine_service.py`.

The flow is:
1. engines scan raw venue / chain / strategy state
2. emit normalized opportunities or intents
3. engine control applies maturity, telemetry, budget, and interference gates
4. admitted items are made compatible with execution capture
5. telemetry records engine decisions and outcomes

## Safety posture

- No engine bypasses execution capture, treasury policy, telemetry, or lifecycle controls.
- Cross-chain remains conservative and inventory-aware.
- MEV remains aligned with private/protected routing and defensive policy.
- Auto-generated strategies remain bounded and lifecycle-gated.
