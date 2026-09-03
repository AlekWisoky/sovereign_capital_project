# OMAR Engineering State

_Last updated: 2026-09-03_

## Mission

Build a genuinely learning autonomous trading system in which real market decisions, real execution, real settled economics, and OMAR learning form one auditable closed loop:

`market data -> strategy/signals -> canonical decision -> governance/admission -> execution -> real fill/P&L/slippage/gas/latency -> canonical settled outcome -> exact action attribution -> OMAR policy update -> next decision`

OMAR is a learning/recommendation subsystem, not a capital, governance, signing, or execution authority.

## Authority invariants

- Canonical decision identity is the source of decision lineage.
- `decision_id -> correlation_id -> execution_id -> settlement_id` must remain intact end-to-end.
- The canonical Phase 2 settled-outcome ledger is the outcome authority.
- `capital_engine_state()` is the actual read-only OMAR capital-authority input.
- Internal-prime economics are represented in stable learning buckets while raw identifiers remain lineage-only.
- Governance/admission remains authoritative and can veto execution.
- OMAR cannot sign, execute, approve capital, or bypass governance/admission.
- Learning is eligible only after a persisted, settled, truth-verified outcome with complete lineage.
- Historical decision intent is write-once; later operator changes affect future decisions, not historical attribution.

## Human/AI intent semantics

The canonical decision context must preserve, at decision time:

- operator control mode;
- bounded aggressiveness posture/risk multiplier;
- brain/learning mode;
- desired wealth goal amount/return target and timeframe;
- AI recommendation context, including opportunity identity and confidence;
- execution/gas preferences where applicable.

These are **context/modifiers**, never authorization. Governance, admission, capital authority, execution safety, freshness, and settlement truth remain higher authority.

## Current implementation state

PR #55 (`codex/omar-production-learning-callback`) contains the production settlement callback wiring. The implemented callback path is:

`canonical decision -> decision/correlation identity -> OMAR decision observation -> execution bookkeeping -> execution identity -> canonical Phase 2 settled ledger -> lineage resolution -> exact action attribution -> policy update`

The branch also includes regression coverage for operator intent, capital authority provenance, canonical outcome consumption, and policy persistence.

## Current verification environment

Termux/Android is **not** the authoritative engineering environment. It has previously been blocked by dependency/native-wheel constraints. Do not use Termux as a prerequisite for formatting or Linux-compatible regression verification.

Authoritative layers:

1. **GitHub Actions / Ubuntu** — formatting, Ruff, mypy, pytest, and contract verification.
2. **Render staging/runtime** — read-only runtime smoke verification of the deployed canonical path; staging must not expose live auto-trading/broadcast authority.
3. **Production** — only after the Linux and staging gates establish the required contracts.

A Linux Black autofix workflow now runs on `codex/**` and `phase/**` branches and commits backend formatting changes with Black 24.10.0. This removes the Termux formatting loop.

## Next engineering gate

After the callback lifecycle is established, the next first-class composition gate is to wire authoritative Phase-A capital-demand composition into the canonical decision path without inventing missing authority:

- compose strategy demand from authoritative treasury/capital state;
- incorporate conversion/provider capacity/fees, exposure, risk, governance, latency/freshness, and execution-plan constraints;
- treat wealth goal and aggressiveness as bounded modifiers;
- treat AI recommendation as evidence/context, never authority;
- fail closed when required authority is unresolved or stale;
- preserve canonical decision identity through execution and settlement;
- feed the settled result back to OMAR with exact attribution.

The repository currently marks this composition area explicitly as `PRODUCTION_COMPOSITION_GAP` / `NOT_PROVEN` where authoritative runtime inputs are not yet wired. Do not turn synthetic tests into claims of production readiness.

## Working rule

Do not ask the user to repeat repository history that is already captured here. When local Termux output is unavailable or unreliable, inspect and modify the repository through GitHub, use GitHub Actions as the Linux verification gate, and use Render for staging/runtime verification.
