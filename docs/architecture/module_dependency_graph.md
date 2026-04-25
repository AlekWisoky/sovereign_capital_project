# Module Dependency Graph

This document describes **high-level module dependencies**. The goal is to keep debugging and maintenance tractable under high cognitive load.

## Backend (RuntimeBundle)

```mermaid
graph TD
  runtime[runtime.py] --> scan[arb_engine.py]
  runtime --> exec[execution.py]
  runtime --> decision[decision_engine.py]
  runtime --> pnl[pnl.py]
  runtime --> cc[command_center_overlay.py]
  runtime --> gov[governance/*]
  runtime --> breakers[circuit_breaker.py]
  runtime --> anomalies[anomaly_breakers.py]
  runtime --> rpc[rpc.py]
  exec --> gas[gas.py]
  exec --> safety[safety.py]
  exec --> calldata[calldata_builder.py]
  decision --> rl[rl_policy.py]
  cc --> audit[(AuditStore JSONL)]
  pnl --> sqlite[(SQLite)]
```

## Mobile

```mermaid
graph TD
  tabs[MainTabs] --> home[HomeCommandScreen]
  tabs --> cap[CapitalStack]
  cap --> capHome[CapitalArchitectureScreen]
  cap --> off[OffRampScreen]
  tabs --> ai[MindOfMachineScreen]
  tabs --> risk[DefensiveLayerScreen]
  tabs --> lab[SandboxLabScreen]
  tabs --> perf[PerformanceScreen]
  tabs --> gov[GovernanceRulesScreen]
  provider[CommandCenter Provider] --> api[api/client.ts]
  screens[All screens] --> provider
```

## Design Rule
Stable core modules must not import experimental overlays.
