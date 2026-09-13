# Sovereign Capital — Institutional Capital Operating System

Sovereign Capital is a governed capital operating system designed to discover market opportunities, evaluate them deterministically, admit only eligible opportunities to capital, size risk under hard constraints, execute through a controlled private path, reconcile actual economics through canonical settlement, learn only from verified outcomes, attribute performance exactly, and promote or retire strategies from evidence.

This repository is the canonical engineering source for the backend runtime, capital/economic controls, execution lifecycle, OMAR learning boundary, mobile operator console, smart-contract test surface, CI verification gate, and staging deployment contract.

> **Engineering posture:** evidence before authority. A feature existing in source code does not mean it is production-authorized. A passing unit test does not authorize live capital. A merged branch does not clear a phase gate until its explicit verification and runtime evidence are complete.

## 1. Current verified repository posture

The current mainline reviewed for this document is:

`6cdfd2398ed8f54cf42201cd1000d81f3d6237d1`

That is the Phase B.4 mainline produced by merged PR #119. Render staging is configured to track `integration/canonical-omar-controlled` and is currently deployed at that same mainline SHA.

The next blocking engineering gate is PR #120, which is **not merged**. Its current head is:

`82234260f00757643f0f2345621df226c52fd08d`

CI run `34738126186` is queued for that exact SHA. Therefore PR #120 is currently **NO GO** for merge. Render must remain on the verified mainline until that exact head completes the Linux gate and the staging/runtime gate is explicitly cleared.

### Current phase map

| Area | Current state | Authority / evidence |
|---|---|---|
| B2 institutional sizing kernel | Merged | PR #115 |
| B3 sizing identity + downstream lineage | Merged | PR #117 |
| B4 final quote / execution binding | Merged | PR #119 |
| B4.5 runtime facade/MRO repair | In verification | PR #120 |
| Mobile canonical backend integration | Incorporated into mainline | PR #93 work carried forward through later merged mobile work |
| Guarded mobile mutations | Merged | PR #99 |
| Realtime reconciliation | Merged | PR #100 |
| F4/I integrated mobile security-contract-lifecycle gate | Remaining | Must follow PR #120/B4.5 runtime clearance |
| Institutional capital-scale residuals | Remaining | Issue #94; reconcile existing B2-B4 work before adding anything |
| Progressive OMAR context + attribution | Remaining | Issue #97 |
| Alpha Marketplace | Remaining | Issue #95 |
| Deterministic MEV/blockspace v2 | Remaining | Issue #96 |
| Live-authority activation | Explicitly blocked | Issue #89 |
| Real-capital flash-arb | Not authorized | Requires #89 and all preceding gates |

---

## 2. System mission

The system is not a collection of independent trading features. It is one governed lifecycle with one authoritative economic path.

Its operating objective is **governed capital compounding**:

- preserve capital as a hard constraint;
- identify repeatable positive expected-value opportunities;
- incorporate gas, slippage, fees, latency, liquidity and failure probability into economics;
- make capital admission deterministic and auditable;
- size downstream of admission rather than letting sizing grant permission;
- reconcile actual capital movement through canonical settlement;
- compare decision-time expectation with verified realized economics;
- learn from expectation error only after settlement verification;
- attribute results to the exact decision, execution, strategy and agent lineage;
- promote capability only when evidence supports it;
- reduce, quarantine or retire deteriorating strategies.

The system must become more capable without becoming less constrained.

---

## 3. Canonical end-to-end blueprint

```text
                           REAL WORLD
                              │
                 ┌────────────┴────────────┐
                 │                         │
             MARKET DATA              BLOCKSPACE
                 │                     INTELLIGENCE
                 └────────────┬────────────┘
                              ▼
                       AQE / SIGNAL LAYER
                              │
                              ▼
                     OPPORTUNITY ENGINE
                              │
                              ▼
                   EXECUTION CAPTURE
             liquidity / route / latency / gas
                              │
                              ▼
                    RESEARCH / AGENT VIEWS
       valuation / fundamentals / sentiment / technicals
        Graham / Ackman / Wood / Munger / Fisher /
              Druckenmiller / Buffett / others
                              │
                              ▼
                    PORTFOLIO MANAGER
                         aggregation only
                              │
                              ▼
                         OMAR CONTEXT
                    recommendation / learning
                              │
                              ▼
                  CANONICAL DECISION ENGINE
       decision_id + correlation_id + intent snapshot
       expected economics + risk envelope + constraints
       opportunity + route + action + agent contributions
                              │
             ┌────────────────┴────────────────┐
             │                                 │
             ▼                                 ▼
     COGNITIVE / HUMAN                 SECURITY / THREAT
       DECISION HYGIENE                     MONITOR
             │                                 │
             └────────────────┬────────────────┘
                              ▼
                    GOVERNANCE / ADMISSION
                 Internal Prime + Risk Control
                              │
                              ▼
                       ADAPTIVE SIZING
                           sizing_id
                              │
                              ▼
                  DETERMINISTIC SIMULATION
                              │
                              ▼
                      PRIVATE EXECUTION
                          execution_id
                              │
                              ▼
                           RECEIPT
                              │
                              ▼
                 CANONICAL SETTLEMENT
             Treasury + Money Loop + Prime
                              │
                              ▼
                    REALIZED ECONOMICS
             net profit / costs / gas / slippage
                              │
                              ▼
                     EXPECTATION ERROR
                realized_net - expected_net
                              │
                              ▼
                       OMAR LEARNING
                              │
                              ▼
                 AGENT / STRATEGY ATTRIBUTION
                              │
                              ▼
                   PROMOTION / RETIREMENT
                              │
                              ▼
                        OOS EVIDENCE
                              │
                              └──────────► next decision
```

There must be no competing execution workflow hidden beside this lifecycle.

---

## 4. Identity model

Identity is deliberately split by lifecycle responsibility.

| Identity | Responsibility | Rule |
|---|---|---|
| `decision_id` | Authoritative decision lifecycle identity | Created by the canonical decision boundary and preserved end-to-end |
| `correlation_id` | Trace/cross-service correlation | Never replaces `decision_id` |
| `opportunity_id` | Opportunity identity | Identifies the candidate being evaluated |
| `route_id` | Route/execution path identity | Attribution only; not authority |
| `sizing_id` | Sizing decision identity | Created by the sizing layer after admission |
| `execution_id` | Execution-attempt identity | Created from existing canonical decision lineage |
| `receipt_id` | Receipt identity | Identifies the execution receipt |
| `outcome_id` | Settled outcome identity | Identifies canonical outcome evidence |
| `strategy_id` | Strategy identity | Stable strategy/genealogy identity; never replaces `decision_id` |
| `agent_id` | Agent contribution identity | Attribution/context only |

No subsystem may introduce a second authoritative transaction or learning identity.

---

## 5. Authority boundaries

### Canonical decision authority

The Decision Engine owns the decision boundary. It freezes material decision-time context, including expected economics, intent, constraints and capital authority context.

OMAR can recommend and provide learning context. It cannot manufacture execution permission.

### Governance / admission authority

Admission answers:

> **May this opportunity use capital?**

The existing `CapitalAdmissionService` remains the admission authority. Governance, hard stops, Internal Prime, risk controls and capital policy constrain this decision.

### Sizing authority

Sizing answers:

> **How much capital may the already-admitted opportunity use?**

Sizing is downstream of admission. It must never become a hidden permission path.

B2-B4 now provide an institutional sizing contract/kernel, sizing identity, and final quote-to-execution binding. Remaining institutional-scale work must extend this architecture rather than replace it.

### Execution authority

V1 real-capital authority is restricted to `flash_arb`. Future strategy families remain observe-only, paper or shadow until explicit promotion.

### Settlement authority

Execution estimates are not economic truth. Canonical settlement is the source of realized economics and capital movement evidence.

### Learning authority

OMAR learning is downstream of verified canonical settlement. A pending execution, optimistic receipt, heuristic profit estimate, or unverified source cannot train the learner.

---

## 6. Economic truth and learning loop

At decision time the system records:

`expected_net_profit`

After canonical settlement it records:

`realized_net_profit`

Then:

`expectation_error = realized_net_profit - expected_net_profit`

Learning requires, at minimum:

- exact `decision_id` lineage;
- matching correlation/action/route attribution;
- valid expected and realized economics;
- finite numeric values;
- verified canonical settlement;
- canonical settlement source;
- physical execution/outcome/sizing/opportunity identities where required;
- no duplicate authoritative learning identity.

The existing learning-integrity boundary explicitly rejects lineage mismatches and unverified/noncanonical settlement sources. fileciteturn326file2

State-local warm-up remains part of the learner contract: insufficient observations use the bounded baseline rather than pretending that a cold learner has evidence.

---

## 7. Capital architecture

Capital is represented through existing canonical services rather than a second portfolio database.

### Treasury

Treasury represents capital movement, balances, liabilities/equity, encumbrance and economic reconciliation.

### Internal Prime

Internal Prime is a capacity/reservation constraint. It is not an additive bankroll and cannot grant execution permission by itself.

### Risk Control

Risk controls constrain execution through hard stops, drawdown controls, family exposure and execution-quality constraints.

### Institutional sizing

The institutional sizing ladder is economic-value aware. Candidate targets such as `$250k`, `$500k`, `$1m+` are policy targets/requests, not unconditional trade amounts.

Final size must remain bounded by the minimum safe result across:

- approved/admitted notional;
- route/provider liquidity;
- pool depth and slippage curve;
- current executable quote;
- expected net economics;
- minimum profit and margin requirements;
- Internal Prime capacity/utilization;
- Treasury deployable capital and buffers;
- family/concentration/drawdown limits;
- execution realism and freshness;
- hard kill switches.

Final raw-unit conversion belongs after final quote/requote, not at an earlier speculative layer.

---

## 8. B2-B4 execution economics currently in main

The merged B2-B4 sequence is important because later work must not redo it.

### B2 — deterministic institutional sizing kernel

PR #115 established the typed sizing kernel while preserving `CapitalAdmissionService` as admission authority and `capital_engine_state()` as capital-authority source.

### B3 — sizing identity and downstream lineage

PR #117 connected the existing sizing kernel to institutional admission and carried its kernel-owned `sizing_id` into the canonical lineage. It also completed the production-shaped execution → receipt → canonical-settlement → learning lineage propagation.

### B4 — final quote binding

PR #119 wired final/requote quote information into production execution. The quote-bound amount is validated before calldata construction/execution and preserves canonical sizing identity.

These phases are merged into main at `6cdfd2398ed8f54cf42201cd1000d81f3d6237d1`. Do not recreate B2/B3/B4 under Issue #94.

---

## 9. OMAR architecture

OMAR is a bounded contextual learning/recommendation subsystem.

It may:

- provide contextual recommendations;
- consume verified settled outcomes;
- update bounded learner state;
- maintain attribution and learning evidence;
- participate in policy/OOS promotion workflows when the relevant gate is satisfied.

It may not:

- create the canonical decision identity;
- authorize capital;
- bypass governance/admission;
- bypass sizing hard caps;
- treat execution estimates as settlement truth;
- learn from pending/unverified outcomes;
- turn conversational input into execution permission.

Issue #97 remains open because the next-decision context still needs a compact, canonical summary of prior settled expectation error, strategy performance, execution realism and blockspace/relay outcomes. The work should enrich the existing state-local learner rather than create a second learning engine.

---

## 10. Agent and research architecture

Research agents provide independent views. They do not execute.

The intended separation is:

```text
Agent views
    ↓
Portfolio Manager
    ↓
OMAR context/recommendation
    ↓
Canonical Decision Engine
    ↓
Governance / Admission
```

Agent consensus, confidence, labels and LLM output are contextual evidence. None is an independent capital authority.

The future Agent Intelligence v2 phase should upgrade the existing AgentHub, contracts, Portfolio Manager, Risk Manager, calibration and attribution surfaces. It must not introduce a parallel agent framework.

---

## 11. Mobile operator architecture

The mobile application is an operator/read surface, not a competing system of record.

Canonical operator surfaces:

```text
HOME
CAPITAL
OPPORTUNITIES
OMAR
RISK
ACTIVITY
```

Mobile responsibilities:

- render canonical backend state;
- expose lineage and economic explanation;
- show freshness/degraded state;
- expose guarded operator controls;
- surface settlement and learning evidence;
- provide decision detail and activity history.

Mobile does not own:

- canonical capital truth;
- canonical decision identity;
- governance/admission;
- sizing permission;
- execution authority;
- canonical settlement;
- OMAR learning authority.

### Guarded mutations

The centralized mutation guard requires the applicable combination of:

- operator role;
- unlocked session;
- admin-key presence;
- backend reachability;
- explicit confirmation;
- backend-reported live authority for live-enable/execution/withdrawal classes.

`auto_trading=true` and `dry_run=false` are treated as activation-shaped mutations.

The backend remains authoritative; mobile is defense in depth.

---

## 12. Realtime architecture

Realtime is an observation accelerator, not a truth authority.

The current boundary is:

```text
Authoritative polling
        │
        ▼
Canonical CommandCenterSnapshot
        │
        ▼
Reconciliation kernel
        ▲
        │
Advisory realtime observations
        ▲
        │
/ws/summary typed transport adapter
```

Rules:

- polling establishes canonical snapshot truth;
- realtime cannot freshen stale canonical polling data;
- transport errors preserve last-known-good canonical state;
- malformed messages are rejected;
- stale/older observations cannot overwrite canonical state;
- the reconciliation path requests complete `summary` frames;
- the adapter does not maintain a second delta-merge state authority;
- no realtime observation can invoke governance, admission, capital, execution or live-authority mutation.

The backend `/ws/summary` producer emits typed `summary`/`delta` envelopes, while mobile consumes the summary path through a narrow adapter. Final semantic signoff still requires paired producer/consumer verification during F4/I.

---

## 13. Bounded cognitive operating system

The cognitive layer is a human decision-hygiene sidecar.

It may expose:

- material decision assumptions;
- uncertainty/confidence;
- disconfirming evidence;
- counterfactuals;
- repeated workflow patterns;
- decision journals;
- postmortems;
- decision latency;
- process adherence.

It must not diagnose hidden psychological states or silently steer capital based on inferred emotions.

The correct telemetry style is observable process evidence, for example:

> `Operator bypassed the normal review sequence 4 times in the last 12 decisions.`

not a speculative psychological diagnosis.

---

## 14. MEV and blockspace safety boundary

The repository already contains MEV/mempool/runtime/search/simulation/private-routing components. Current heuristic MEV economics are deliberately non-authoritative and the current safety floor is observe-only.

Issue #96 is the next serious MEV engineering phase. It must add evidence-backed deterministic fork simulation, perturbation testing, private/protected routing telemetry and relay/builder reliability without creating a second execution workflow.

No public sandwich/front-run execution is part of the approved architecture.

---

## 15. Alpha Marketplace boundary

Issue #95 will turn the existing alpha marketplace into an internal evidence and promotion layer.

The intended flow is:

```text
AQE / existing strategy factory
        ↓
StrategyCandidate
        ↓
Sandbox / paper / shadow evidence
        ↓
Alpha Marketplace
        ↓
Governance + engine-control promotion
        ↓
Capital sleeve proposal
        ↓
Internal Prime / Treasury reservation
        ↓
Canonical Decision
        ↓
Existing execution lifecycle
        ↓
Canonical settlement
        ↓
Strategy + agent attribution
        ↓
OMAR learning
```

`strategy_id` is a stable strategy identity. It never replaces `decision_id`.

---

## 16. Current phase gates

### Gate 1 — PR #120 / B4.5 runtime repair

**Current status: NO GO.**

The runtime facade MRO repair removes concrete-authority shadowing that caused `/api/commandcenter/snapshot` to fail. A subsequent CI failure exposed a deeper capital-truth re-entry path. The current repair uses a context-local re-entry guard rather than a runtime-owned cache, minimizing dependency surface.

The exact head is:

`82234260f00757643f0f2345621df226c52fd08d`

CI:

`34738126186`

The gate is not cleared until all pytest shards, backend quality, mobile, contracts and artifact checks are green on that exact SHA.

### Gate 2 — Render staging identity

After PR #120 is green and merged:

1. record the exact merge SHA;
2. verify `integration/canonical-omar-controlled` points to that SHA;
3. let Render auto-deploy;
4. verify Render's deployment commit identity;
5. perform read-only runtime smoke only.

Required smoke surfaces:

```text
/health
/api/deploy/info
/api/state
/api/commandcenter/snapshot
/api/engines/state
/api/brain/state
```

Then verify staging remains non-live: no live broadcast authority, no automatic trading authority, no withdrawal/signing activation.

### Gate 3 — F4/I

Complete the integrated security, backend-contract and lifecycle review:

- every mutation has one guarded path;
- locked/read-only/missing-key/unreachable cases fail closed;
- explicit confirmations cover activation-shaped controls;
- emergency-stop lifecycle is reviewed;
- session/reconnect timers are cleaned up;
- backend contracts match actual producer schemas;
- realtime cannot become authorization;
- secrets do not enter telemetry;
- malformed/stale/duplicate observations cannot corrupt canonical state.

### Gate 4 — residual Issue #94

Only after Phase A/F4/I is green, reconcile Issue #94 against already-merged B2-B4 before implementing anything. The likely remaining scope is capital-scale policy, promotion criteria, stress evidence, hard-cap behavior and institutional capacity reporting—not a new sizing kernel.

### Later gates

```text
#94 residual institutional scale
        ↓
#97 progressive OMAR context + attribution
        ↓
Agent Intelligence v2
        ↓
#95 Alpha Marketplace
        ↓
#96 deterministic MEV / blockspace
        ↓
Research / Evolution
        ↓
visual/operator production pass
        ↓
integrated mobile/backend validation
        ↓
#89 live-authority review
        ↓
capped real flash-arb validation
        ↓
institutional scaling
```

---

## 17. Issue #89 — explicit live-authority gate

Issue #89 remains an independent operational authorization gate.

Before any real capital:

1. review `dry_run` / `auto_trading` changes under controlled approval;
2. verify private/protected submission lane configuration;
3. verify wallet/executor/chain/signer/destination configuration;
4. verify runtime/admin/operator authorization;
5. prove `flash_arb` / `flashloan_atomic` remains the only V1 live family;
6. rerun health/startup/runtime safety gates after activation changes;
7. execute one deliberately capped transaction only after all preceding evidence is green;
8. verify receipt and canonical settlement;
9. verify realized economics and exact expectation error;
10. verify OMAR learning is attributed to the exact settled decision lineage;
11. record rollback/kill-switch evidence.

No amount of UI completeness or CI success substitutes for this gate.

---

## 18. Deployment and verification model

### GitHub Actions — canonical verification

Linux GitHub Actions is the authoritative test environment because the local Termux environment is intentionally not treated as capable of running the full project suite.

The CI contract includes:

- backend quality checks;
- Python compile validation;
- configured mypy targets;
- Ruff;
- 8-way pytest sharding;
- mobile typecheck/unit tests/build;
- Foundry contract tests;
- deterministic verification/system-truth artifact generation.

The pytest matrix preserves the complete test inventory. Sharding is a verification-performance mechanism, not a test exclusion mechanism.

### Render — staging/runtime verification

Render is the staging/runtime layer. It is used only after a specific commit has passed the GitHub gate.

The canonical staging service is:

`sovereign-capital`

Branch:

`integration/canonical-omar-controlled`

Health path:

`/health`

Staging is non-authoritative and must remain non-live.

### Termux

Termux is inspection/minimum-repair only. It is not the project verification authority.

### Observability

Sentry is observability only. It must never become a dependency of capital authorization, signing, execution, settlement or learning.

Code quality signals such as CodeScene comments are advisory engineering evidence. They must not override repository tests or architectural authority contracts.

---

## 19. Generated truth and reproducibility

Generated system truth is deterministic repository evidence.

Important generators include:

```text
scripts/render_system_truth.py
scripts/render_verification_report.py
```

When source inventory changes, regenerate the artifacts using the repository generators. Do not manually edit generated truth to make a verification result look current.

CI must validate generated truth; it must not permanently mutate the PR branch.

---

## 20. Repository layout

```text
backend/
  victor_ai_bot/
    api_routes/                 HTTP/WebSocket boundaries
    decision/                   canonical decision logic
    execution/                  execution boundary
    execution_capture/          execution/economic observation and sizing
    governance/                 hard safety and admission controls
    omar/                       bounded learning/recommendation subsystem
    aqe/                        opportunity / signal / MEV intelligence
    runtime_services/           canonical runtime service boundaries
    persistence/                durable repositories / ledgers
    treasury/                   treasury economics and capital accounting
    superstructure/             operator/governance projections

backend/tests/                  authoritative backend regression inventory
contracts/                      Foundry contracts and contract tests
mobile/
  src/api/                      canonical backend adapters
  src/                          operator UI, guards, reconciliation, wallet lifecycle
  tests/                        mobile unit/contract tests
docs/                           architecture, contracts, deployment and gate documentation
scripts/                        deterministic generated-truth tooling
.github/workflows/ci.yml        Linux verification pipeline
Dockerfile                      staging/runtime container contract
```

---

## 21. Engineering rules for future contributors

Before changing code:

1. identify the existing authority;
2. inspect the relevant service and its tests;
3. inspect its callers and downstream lineage;
4. determine whether the change is a projection, dependency read, authority decision, or mutation;
5. preserve the canonical identity and economic source of truth;
6. add the smallest regression proving the concrete defect;
7. run the authoritative Linux gate;
8. inspect actual failures rather than weakening tests;
9. verify generated truth through its generator;
10. only then move the change into Render staging.

Never:

- create a second capital ledger;
- create a second decision engine;
- create a second learning identity;
- let OMAR execute;
- let realtime overwrite canonical polling truth;
- let a risk label grant permission;
- let human approval bypass hard controls;
- let heuristic economics authorize execution;
- promote a future strategy family merely because its code exists;
- enable live trading because staging or CI is green;
- merge a phase because the branch merely exists.

---

## 22. Known open gaps

The system is not yet an end-to-end live institutional trading OS. The current explicit gaps include:

- PR #120/B4.5 Linux and runtime verification is not yet green;
- F4/I mobile security-contract-lifecycle gate remains to be completed;
- the exact producer/consumer semantic verification of `/ws/summary` must be finalized;
- Issue #94 still needs residual institutional capital-scale policy and stress/promotion evidence after reconciliation with B2-B4;
- Issue #97 needs richer settlement-derived prior-outcome context and attribution;
- Issue #95 remains a future evidence/promotion layer;
- Issue #96 remains a future deterministic MEV/blockspace layer;
- external-wallet withdrawal still requires the final guarded submission/reconciliation lifecycle to be verified end-to-end;
- Issue #89 live-authority activation review remains mandatory;
- no real-capital execution is authorized by this README or by code presence alone.

These are explicit engineering gates, not invitations to create parallel implementations.

---

## 23. Definition of done

Sovereign Capital is considered a coherent institutional operating system only when this complete loop is joined and verified:

```text
market
 → signal
 → opportunity
 → research
 → portfolio aggregation
 → OMAR context
 → canonical decision
 → governance/admission
 → Internal Prime / Risk
 → adaptive sizing
 → deterministic simulation
 → execution
 → receipt
 → canonical settlement
 → realized economics
 → expectation error
 → OMAR learning
 → exact strategy/agent attribution
 → promotion/retirement
 → OOS evidence
 → next governed decision
```

And when all of the following remain true:

- capital mutations are fail-closed;
- settlement is economic truth;
- decision identity is singular;
- realtime is advisory;
- mobile is not a competing authority;
- future strategy families are blocked until promoted;
- institutional size is evidence-backed and hard-capped;
- live authority is explicitly reviewed;
- deployment identity is reproducible;
- GitHub Linux is green for the exact verified SHA;
- Render staging has been read-only verified against that SHA;
- the capped live flash-arb gate has independently passed before institutional scaling.

**Current operational command:** verify PR #120 exact head → merge only after green → align Render → read-only smoke → close B4.5 → execute F4/I → reconcile #94 residuals → continue the remaining evidence gates.
