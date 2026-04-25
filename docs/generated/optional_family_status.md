# Optional family status

- Contract: optional_family_status_v2
- Classification engine: automatic_runtime_reachability_v3
- Evidence policy: status derives only from mounted routes, runtime initialization, import reachability, and gating conditions; tests and docs are supplemental evidence only
- Status counts: {"dead": 7, "live": 11, "shadow": 3, "staged": 2}

| Family | Status | Py files | Refs | Primary evidence | Mounted | Runtime init | Imports | Gating |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| alpha_marketplace | staged | 4 | 5 | 4 | 0 | 1 | 2 | 1 |

Runtime or server reachability exists, but only behind explicit gating or optional initialization.

- **alpha_marketplace runtimeInitialization**
  - backend/victor_ai_bot/runtime_services/runtime_institutional_init.py
- **alpha_marketplace importReachability**
  - backend/tests/test_fund_os_upgrade.py
  - backend/victor_ai_bot/runtime_services/runtime_institutional_init.py
- **alpha_marketplace gatingConditions**
  - backend/victor_ai_bot/runtime_services/runtime_institutional_init.py
- **alpha_marketplace tests**
  - backend/tests/test_fund_os_upgrade.py

| alpha_platform | live | 7 | 7 | 5 | 0 | 1 | 4 | 0 |

Mounted routes or ungated runtime initialization establish live reachability.

- **alpha_platform runtimeInitialization**
  - backend/victor_ai_bot/runtime_services/fund_service.py
- **alpha_platform importReachability**
  - backend/tests/test_fund_os_upgrade.py
  - backend/tests/test_multistrategy_fund_upgrade.py
  - backend/victor_ai_bot/fund_os/master_orchestrator.py
  - backend/victor_ai_bot/runtime_services/fund_service.py
- **alpha_platform tests**
  - backend/tests/test_fund_os_upgrade.py
  - backend/tests/test_multistrategy_fund_upgrade.py

| aqe | live | 86 | 61 | 35 | 0 | 3 | 32 | 0 |

Mounted routes or ungated runtime initialization establish live reachability.

- **aqe runtimeInitialization**
  - backend/victor_ai_bot/runtime_services/engine_service.py
  - backend/victor_ai_bot/runtime_services/runtime_execution_support_init.py
  - backend/victor_ai_bot/runtime_services/runtime_optional_family_init.py
- **aqe importReachability**
  - backend/tests/test_95plus_realism.py
  - backend/tests/test_adaptation_maintenance.py
  - backend/tests/test_agent_hub_maintenance.py
  - backend/tests/test_agents_system.py
  - backend/tests/test_aqe_core_actions.py
  - backend/tests/test_aqe_import_boundary.py
  - backend/tests/test_arbitrage_adapters_hardening.py
  - backend/tests/test_arbitrage_runtime_hardening.py
- **aqe tests**
  - backend/tests/test_95plus_realism.py
  - backend/tests/test_adaptation_maintenance.py
  - backend/tests/test_agent_hub_maintenance.py
  - backend/tests/test_agents_system.py
  - backend/tests/test_aqe_core_actions.py
  - backend/tests/test_aqe_import_boundary.py
  - backend/tests/test_arbitrage_adapters_hardening.py
  - backend/tests/test_arbitrage_runtime_hardening.py

| backtest | shadow | 2 | 4 | 2 | 0 | 0 | 2 | 0 |

External imports establish reachability, but no mounted-route or runtime-init proof was found.

- **backtest importReachability**
  - backend/tests/test_backtest_replay_maintenance.py
  - backend/tests/test_profitability_truth_selection_sync.py
- **backtest tests**
  - backend/tests/test_backtest_replay_maintenance.py
  - backend/tests/test_profitability_truth_selection_sync.py

| behaveagent | live | 8 | 6 | 5 | 0 | 1 | 4 | 0 |

Mounted routes or ungated runtime initialization establish live reachability.

- **behaveagent runtimeInitialization**
  - backend/victor_ai_bot/runtime_services/runtime_execution_support_init.py
- **behaveagent importReachability**
  - backend/tests/test_behaveagent_runtime_maintenance.py
  - backend/victor_ai_bot/config.py
  - backend/victor_ai_bot/runtime.py
  - backend/victor_ai_bot/runtime_services/runtime_execution_support_init.py
- **behaveagent tests**
  - backend/tests/test_behaveagent_runtime_maintenance.py

| caq_kds | live | 8 | 46 | 41 | 1 | 10 | 30 | 0 |

Mounted routes or ungated runtime initialization establish live reachability.

- **caq_kds mountedRoutes**
  - backend/victor_ai_bot/api_routes/intelligence_routes.py
- **caq_kds runtimeInitialization**
  - backend/victor_ai_bot/runtime_services/execution_service.py
  - backend/victor_ai_bot/runtime_services/receipt_service.py
  - backend/victor_ai_bot/runtime_services/runtime_agent_consensus_facade.py
  - backend/victor_ai_bot/runtime_services/runtime_caq_kds_facade.py
  - backend/victor_ai_bot/runtime_services/runtime_feature_bus_facade.py
  - backend/victor_ai_bot/runtime_services/runtime_market_facade.py
  - backend/victor_ai_bot/runtime_services/runtime_post_tick_facade.py
  - backend/victor_ai_bot/runtime_services/runtime_predecision_state_facade.py
- **caq_kds importReachability**
  - backend/tests/test_caq_kds_intelligence_maintenance.py
  - backend/tests/test_caq_kds_self_evolution_maintenance.py
  - backend/tests/test_gmao_governance_maintenance.py
  - backend/tests/test_stage22_rag_context_hardening.py
  - backend/tests/test_stage24_multimodal_context_hardening.py
  - backend/victor_ai_bot/api_routes/intelligence_routes.py
  - backend/victor_ai_bot/aqe/arbitrage/runtime.py
  - backend/victor_ai_bot/aqe/coordination/feature_bus.py
- **caq_kds tests**
  - backend/tests/test_caq_kds_intelligence_maintenance.py
  - backend/tests/test_caq_kds_self_evolution_maintenance.py
  - backend/tests/test_gmao_governance_maintenance.py
  - backend/tests/test_stage22_rag_context_hardening.py
  - backend/tests/test_stage24_multimodal_context_hardening.py

| cex_connectors | dead | 4 | 0 | 0 | 0 | 0 | 0 | 0 |

No mounted-route, runtime-init, or external import reachability was found outside the subsystem tree.


| desk_runtime | dead | 3 | 0 | 0 | 0 | 0 | 0 | 0 |

No mounted-route, runtime-init, or external import reachability was found outside the subsystem tree.


| evolution | live | 7 | 5 | 4 | 1 | 0 | 3 | 0 |

Mounted routes or ungated runtime initialization establish live reachability.

- **evolution mountedRoutes**
  - backend/victor_ai_bot/api_routes/evolution.py
- **evolution importReachability**
  - backend/tests/test_evolution_lifecycle.py
  - backend/victor_ai_bot/api_routes/__init__.py
  - backend/victor_ai_bot/aqe/meta/runtime.py
- **evolution tests**
  - backend/tests/test_evolution_lifecycle.py

| fioa | live | 4 | 9 | 7 | 0 | 1 | 6 | 0 |

Mounted routes or ungated runtime initialization establish live reachability.

- **fioa runtimeInitialization**
  - backend/victor_ai_bot/runtime_services/runtime_optional_overlay_init.py
- **fioa importReachability**
  - backend/tests/test_fioa_audit_maintenance.py
  - backend/tests/test_fioa_runtime_maintenance.py
  - backend/victor_ai_bot/config.py
  - backend/victor_ai_bot/llm_inl/runtime.py
  - backend/victor_ai_bot/runtime.py
  - backend/victor_ai_bot/runtime_services/runtime_optional_overlay_init.py
- **fioa tests**
  - backend/tests/test_fioa_audit_maintenance.py
  - backend/tests/test_fioa_runtime_maintenance.py

| funding_arb | dead | 6 | 0 | 0 | 0 | 0 | 0 | 0 |

No mounted-route, runtime-init, or external import reachability was found outside the subsystem tree.


| liquidations | dead | 8 | 0 | 0 | 0 | 0 | 0 | 0 |

No mounted-route, runtime-init, or external import reachability was found outside the subsystem tree.


| llm_inl | live | 3 | 10 | 7 | 0 | 1 | 6 | 0 |

Mounted routes or ungated runtime initialization establish live reachability.

- **llm_inl runtimeInitialization**
  - backend/victor_ai_bot/runtime_services/runtime_optional_overlay_init.py
- **llm_inl importReachability**
  - backend/tests/test_fioa_audit_maintenance.py
  - backend/tests/test_llm_inl_runtime_maintenance.py
  - backend/tests/test_profitability_projection_auxiliary_sync.py
  - backend/victor_ai_bot/config.py
  - backend/victor_ai_bot/runtime.py
  - backend/victor_ai_bot/runtime_services/runtime_optional_overlay_init.py
- **llm_inl tests**
  - backend/tests/test_fioa_audit_maintenance.py
  - backend/tests/test_llm_inl_runtime_maintenance.py
  - backend/tests/test_profitability_projection_auxiliary_sync.py

| market_making | shadow | 5 | 2 | 1 | 0 | 0 | 1 | 0 |

External imports establish reachability, but no mounted-route or runtime-init proof was found.

- **market_making importReachability**
  - backend/tests/test_multistrategy_fund_upgrade.py
- **market_making tests**
  - backend/tests/test_multistrategy_fund_upgrade.py

| mev | dead | 6 | 0 | 0 | 0 | 0 | 0 | 0 |

No mounted-route, runtime-init, or external import reachability was found outside the subsystem tree.


| omar | staged | 11 | 6 | 5 | 0 | 1 | 3 | 1 |

Runtime or server reachability exists, but only behind explicit gating or optional initialization.

- **omar runtimeInitialization**
  - backend/victor_ai_bot/server.py
- **omar importReachability**
  - backend/tests/test_omar_runtime.py
  - backend/victor_ai_bot/runtime.py
  - backend/victor_ai_bot/server.py
- **omar gatingConditions**
  - backend/victor_ai_bot/server.py
- **omar tests**
  - backend/tests/test_omar_runtime.py

| pod_runtime | dead | 3 | 0 | 0 | 0 | 0 | 0 | 0 |

No mounted-route, runtime-init, or external import reachability was found outside the subsystem tree.


| research_pipeline | live | 8 | 12 | 9 | 1 | 2 | 6 | 0 |

Mounted routes or ungated runtime initialization establish live reachability.

- **research_pipeline mountedRoutes**
  - backend/victor_ai_bot/api_routes/fund_routes.py
- **research_pipeline runtimeInitialization**
  - backend/victor_ai_bot/runtime_services/fund_service.py
  - backend/victor_ai_bot/runtime_services/runtime_institutional_init.py
- **research_pipeline importReachability**
  - backend/tests/test_fund_os_upgrade.py
  - backend/tests/test_fund_research_routes_maintenance.py
  - backend/tests/test_research_workspace.py
  - backend/victor_ai_bot/api_routes/fund_routes.py
  - backend/victor_ai_bot/runtime_services/fund_service.py
  - backend/victor_ai_bot/runtime_services/runtime_institutional_init.py
- **research_pipeline tests**
  - backend/tests/test_fund_os_upgrade.py
  - backend/tests/test_fund_research_routes_maintenance.py
  - backend/tests/test_research_workspace.py

| rft | live | 17 | 15 | 10 | 1 | 1 | 8 | 0 |

Mounted routes or ungated runtime initialization establish live reachability.

- **rft mountedRoutes**
  - backend/victor_ai_bot/api_routes/rft.py
- **rft runtimeInitialization**
  - backend/victor_ai_bot/runtime_subsystems/replay_store.py
- **rft importReachability**
  - backend/tests/test_api_rft_and_wealth.py
  - backend/tests/test_rft_graders.py
  - backend/tests/test_rft_ids.py
  - backend/tests/test_rft_routes_hardening_maintenance.py
  - backend/tests/test_rft_schema.py
  - backend/victor_ai_bot/api_routes/__init__.py
  - backend/victor_ai_bot/api_routes/rft.py
  - backend/victor_ai_bot/runtime_subsystems/replay_store.py
- **rft tests**
  - backend/tests/test_api_rft_and_wealth.py
  - backend/tests/test_rft_graders.py
  - backend/tests/test_rft_ids.py
  - backend/tests/test_rft_routes_hardening_maintenance.py
  - backend/tests/test_rft_schema.py

| rl_training | live | 6 | 8 | 6 | 0 | 2 | 4 | 0 |

Mounted routes or ungated runtime initialization establish live reachability.

- **rl_training runtimeInitialization**
  - backend/victor_ai_bot/runtime_services/runtime_institutional_init.py
  - backend/victor_ai_bot/runtime_subsystems/reward_trace.py
- **rl_training importReachability**
  - backend/tests/test_multistrategy_fund_upgrade.py
  - backend/tests/test_risk_reward_upgrades.py
  - backend/victor_ai_bot/runtime_services/runtime_institutional_init.py
  - backend/victor_ai_bot/runtime_subsystems/reward_trace.py
- **rl_training tests**
  - backend/tests/test_multistrategy_fund_upgrade.py
  - backend/tests/test_risk_reward_upgrades.py

| simulator | dead | 4 | 0 | 0 | 0 | 0 | 0 | 0 |

No mounted-route, runtime-init, or external import reachability was found outside the subsystem tree.


| stat_arb | shadow | 5 | 2 | 1 | 0 | 0 | 1 | 0 |

External imports establish reachability, but no mounted-route or runtime-init proof was found.

- **stat_arb importReachability**
  - backend/tests/test_multistrategy_fund_upgrade.py
- **stat_arb tests**
  - backend/tests/test_multistrategy_fund_upgrade.py

| superstructure | live | 13 | 24 | 14 | 0 | 1 | 13 | 0 |

Mounted routes or ungated runtime initialization establish live reachability.

- **superstructure runtimeInitialization**
  - backend/victor_ai_bot/runtime_services/runtime_optional_overlay_init.py
- **superstructure importReachability**
  - backend/tests/test_capital_maintenance.py
  - backend/tests/test_gmao_governance_maintenance.py
  - backend/tests/test_negotiation_maintenance.py
  - backend/tests/test_path_planning_maintenance.py
  - backend/tests/test_profitability_projection_auxiliary_sync.py
  - backend/tests/test_registry_maintenance.py
  - backend/tests/test_stability_maintenance.py
  - backend/tests/test_superstructure_command_center_maintenance.py
- **superstructure tests**
  - backend/tests/test_capital_maintenance.py
  - backend/tests/test_gmao_governance_maintenance.py
  - backend/tests/test_negotiation_maintenance.py
  - backend/tests/test_path_planning_maintenance.py
  - backend/tests/test_profitability_projection_auxiliary_sync.py
  - backend/tests/test_registry_maintenance.py
  - backend/tests/test_stability_maintenance.py
  - backend/tests/test_superstructure_command_center_maintenance.py
