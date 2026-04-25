from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator


class PersistenceDB:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS telemetry_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chain TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    ts_ms INTEGER NOT NULL,
                    route_family TEXT,
                    strategy_family TEXT,
                    regime TEXT,
                    lane TEXT,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_telemetry_chain_type_ts ON telemetry_events(chain, event_type, ts_ms DESC);
                CREATE INDEX IF NOT EXISTS idx_telemetry_route_lane ON telemetry_events(route_family, lane, ts_ms DESC);

                CREATE TABLE IF NOT EXISTS agent_attribution (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chain TEXT NOT NULL,
                    ts_ms INTEGER NOT NULL,
                    opportunity_id TEXT,
                    route_id TEXT,
                    strategy_family TEXT,
                    agent TEXT NOT NULL,
                    followed INTEGER NOT NULL,
                    realized_pnl_impact_usd REAL NOT NULL,
                    precision_hit INTEGER NOT NULL,
                    regime TEXT,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_agent_attr_chain_agent_ts ON agent_attribution(chain, agent, ts_ms DESC);

                CREATE TABLE IF NOT EXISTS family_scorecards (
                    chain TEXT NOT NULL,
                    family TEXT NOT NULL,
                    count INTEGER NOT NULL,
                    realized_pnl_usd REAL NOT NULL,
                    gas_cost_usd REAL NOT NULL,
                    successes INTEGER NOT NULL,
                    drawdown_penalty REAL NOT NULL,
                    correlation_penalty REAL NOT NULL,
                    regimes_json TEXT NOT NULL,
                    PRIMARY KEY(chain, family)
                );

                CREATE TABLE IF NOT EXISTS execution_calibration (
                    chain TEXT NOT NULL,
                    route_family TEXT NOT NULL,
                    lane TEXT NOT NULL,
                    regime TEXT NOT NULL DEFAULT '',
                    count INTEGER NOT NULL,
                    projected_realized_edge_usd REAL NOT NULL,
                    actual_realized_edge_usd REAL NOT NULL,
                    predicted_success_probability REAL NOT NULL,
                    actual_successes INTEGER NOT NULL,
                    predicted_slippage_usd REAL NOT NULL,
                    actual_slippage_usd REAL NOT NULL,
                    predicted_interference_probability REAL NOT NULL,
                    actual_stales INTEGER NOT NULL,
                    PRIMARY KEY(chain, route_family, lane, regime)
                );

                CREATE TABLE IF NOT EXISTS security_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_ms INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    subject TEXT,
                    chain TEXT,
                    allowed INTEGER NOT NULL,
                    capability TEXT,
                    details_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS venue_profiles (
                    chain TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    count INTEGER NOT NULL,
                    successes INTEGER NOT NULL,
                    failures INTEGER NOT NULL,
                    stale_quotes INTEGER NOT NULL,
                    total_slippage_bias REAL NOT NULL,
                    total_latency_ms REAL NOT NULL,
                    route_success_contribution REAL NOT NULL,
                    PRIMARY KEY(chain, venue)
                );

                CREATE TABLE IF NOT EXISTS treasury_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chain TEXT NOT NULL,
                    ts_ms INTEGER NOT NULL,
                    utilization_rate REAL NOT NULL,
                    deployed_capital_wei INTEGER NOT NULL,
                    idle_capital_wei INTEGER NOT NULL,
                    return_on_deployed REAL NOT NULL,
                    return_on_at_risk REAL NOT NULL,
                    failure_adjusted_efficiency REAL NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_treasury_chain_ts ON treasury_metrics(chain, ts_ms DESC);


                CREATE TABLE IF NOT EXISTS bankroll_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chain TEXT NOT NULL,
                    ts_ms INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    realized_profit_wei INTEGER NOT NULL,
                    last_amount_in_wei INTEGER NOT NULL,
                    success_streak INTEGER NOT NULL,
                    fail_streak INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_bankroll_events_chain_ts ON bankroll_events(chain, ts_ms DESC, id DESC);

                CREATE TABLE IF NOT EXISTS treasury_state_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chain TEXT NOT NULL,
                    ts_ms INTEGER NOT NULL,
                    state_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_treasury_state_chain_type_ts ON treasury_state_history(chain, state_type, ts_ms DESC, id DESC);

                CREATE TABLE IF NOT EXISTS capital_event_bus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chain TEXT NOT NULL,
                    ts_ms INTEGER NOT NULL,
                    domain TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    transaction_id TEXT NOT NULL,
                    receipt_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_capital_event_bus_chain_domain_ts ON capital_event_bus(chain, domain, ts_ms DESC, id DESC);
                CREATE INDEX IF NOT EXISTS idx_capital_event_bus_chain_source_ts ON capital_event_bus(chain, source, ts_ms DESC, id DESC);
                CREATE INDEX IF NOT EXISTS idx_capital_event_bus_chain_receipt ON capital_event_bus(chain, receipt_id, ts_ms DESC, id DESC);

                CREATE TABLE IF NOT EXISTS internal_prime_state_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chain TEXT NOT NULL,
                    ts_ms INTEGER NOT NULL,
                    state_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_internal_prime_state_chain_type_ts ON internal_prime_state_history(chain, state_type, ts_ms DESC, id DESC);

                CREATE TABLE IF NOT EXISTS lifecycle_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chain TEXT NOT NULL,
                    ts_ms INTEGER NOT NULL,
                    family TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_lifecycle_chain_family_ts ON lifecycle_history(chain, family, ts_ms DESC);

                CREATE TABLE IF NOT EXISTS execution_edge_metrics (
                    chain TEXT NOT NULL,
                    route_family TEXT NOT NULL,
                    lane TEXT NOT NULL,
                    regime TEXT NOT NULL DEFAULT '',
                    count INTEGER NOT NULL,
                    projected_gross_edge_usd REAL NOT NULL,
                    projected_realized_edge_usd REAL NOT NULL,
                    actual_realized_edge_usd REAL NOT NULL,
                    PRIMARY KEY(chain, route_family, lane, regime)
                );
                

                CREATE TABLE IF NOT EXISTS edge_model_priors (
                    chain TEXT NOT NULL,
                    key TEXT NOT NULL,
                    family TEXT NOT NULL,
                    route_family TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    lane TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    count INTEGER NOT NULL,
                    success_ewma REAL NOT NULL,
                    competition_ewma REAL NOT NULL,
                    quality_ewma REAL NOT NULL,
                    freshness_ewma REAL NOT NULL,
                    slippage_bias_ewma REAL NOT NULL,
                    failure_risk_ewma REAL NOT NULL,
                    updated_ts_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(chain, key)
                );
                CREATE INDEX IF NOT EXISTS idx_edge_priors_family ON edge_model_priors(chain, family, updated_ts_ms DESC);

                CREATE TABLE IF NOT EXISTS edge_model_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chain TEXT NOT NULL,
                    family TEXT NOT NULL,
                    route_family TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    lane TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    ts_ms INTEGER NOT NULL,
                    feature_json TEXT NOT NULL,
                    prediction_json TEXT NOT NULL,
                    outcome_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_edge_obs_chain_family_ts ON edge_model_observations(chain, family, ts_ms DESC);

                CREATE TABLE IF NOT EXISTS launch_state (
                    chain TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_ts_ms INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS capital_recovery_state (
                    chain TEXT NOT NULL,
                    component TEXT NOT NULL,
                    is_degraded INTEGER NOT NULL,
                    degraded_since_ts_ms INTEGER NOT NULL,
                    last_recovered_ts_ms INTEGER NOT NULL,
                    updated_ts_ms INTEGER NOT NULL,
                    last_reason_code TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(chain, component)
                );
                CREATE INDEX IF NOT EXISTS idx_capital_recovery_chain_component ON capital_recovery_state(chain, component);
                

                CREATE TABLE IF NOT EXISTS auto_trade_recovery_state (
                    chain TEXT NOT NULL,
                    component TEXT NOT NULL,
                    is_degraded INTEGER NOT NULL,
                    degraded_since_ts_ms INTEGER NOT NULL,
                    last_recovered_ts_ms INTEGER NOT NULL,
                    updated_ts_ms INTEGER NOT NULL,
                    last_reason_code TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(chain, component)
                );
                CREATE INDEX IF NOT EXISTS idx_auto_trade_recovery_chain_component ON auto_trade_recovery_state(chain, component);


                CREATE TABLE IF NOT EXISTS auto_trade_recovery_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chain TEXT NOT NULL,
                    component TEXT NOT NULL,
                    ts_ms INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    blocker_component TEXT NOT NULL,
                    next_action TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_auto_trade_recovery_events_chain_component_ts ON auto_trade_recovery_events(chain, component, ts_ms DESC, id DESC);
                """
            )
