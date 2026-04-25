# x∆v — Sovereign Capital
## 9.2+ remediation architecture map

### Runtime ownership after this upgrade

- `runtime.py`
  - orchestration shell / lifecycle / compatibility
  - delegates to bounded services and subsystems
- `runtime_services/opportunity_service.py`
  - strategy-family annotation
  - regime-aware opportunity metadata
- `execution_capture/*`
  - execution-first decisioning, calibration, route priors, no-trade analytics
- `telemetry/*`
  - rich event storage, feedback summaries, learning substrate
- `agents/*`
  - mandates, health, attribution, weighting, regime-specific relevance
- `treasury/*`
  - capital buckets, family allocation, reinvestment policy, capital efficiency
- `evolution/*`
  - genealogy, diversity pressure, lifecycle, retirement reasons, validation
- `strategies/*`
  - family metadata, scorecards, regime binding, interaction controls
- `api_routes/*`
  - domain-split API surfaces for agents, treasury, telemetry, strategies, evolution, RFT

### Data feedback loops

1. opportunity discovered
2. strategy-family metadata attached
3. agent hub evaluates and publishes weighted/health-tagged outputs
4. capture engine scores route with empirical priors + telemetry
5. capital engine constrains family-level deployment
6. execution decision admits / downsizes / reroutes / drops
7. receipt/outcome recorded into telemetry, calibration, family scorecards, agent attribution
8. telemetry summaries feed future capture scoring, agent weighting, and strategy lifecycle decisions

### Safety boundaries

- execution remains bounded by existing executor + safety gates
- agent outputs are advisory and attributable, not unbounded authority
- evolution remains config-gated and promotion-limited
- full-system mode does not bypass risk/capital/governance gates
