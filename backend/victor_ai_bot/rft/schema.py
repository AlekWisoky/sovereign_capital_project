from __future__ import annotations

from typing import Any, Dict, Final, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..capital_demand import CapitalDemand
from ..version import __version__ as BACKEND_BUILDER_VERSION

PROPOSAL_SCHEMA_VERSION: Final[Literal["1"]] = "1"


class ProposalConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_slippage_bps: int = Field(ge=0, le=10_000)
    deadline_seconds: int = Field(ge=1, le=3_600)


class ProposalMode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sandbox_only: bool = False
    defensive: bool = False
    probation: bool = False


class ProposalOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_schema_version: Literal["1"] = PROPOSAL_SCHEMA_VERSION
    backend_builder_version: str = BACKEND_BUILDER_VERSION
    opportunity_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    notional_usd_micro: int = Field(ge=0)
    send_mode: Literal["protected_rpc", "public", "txdata"]
    why: List[str] = Field(default_factory=list, min_length=1)
    constraints: ProposalConstraints
    mode: ProposalMode

    @classmethod
    def json_schema_draft07(cls) -> Dict[str, Any]:
        schema = cls.model_json_schema()
        schema["$schema"] = "http://json-schema.org/draft-07/schema#"
        return schema


class RiskCaps(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_daily_loss_pct_bps: int = 300
    max_exposure_pct_bps: int = 8_000
    sandbox_cap_pct_bps: int = 1_000
    probation_cap_pct_bps: int = 250


class BreakerState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    drawdown_breaker: bool = False
    gas_anomaly_breaker: bool = False
    drift_breaker: bool = False
    rpc_degraded: bool = False


class LatencyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loop_ms_p50: int = 0
    loop_ms_p90: int = 0
    loop_ms_p99: int = 0
    exec_ms_p50: int = 0
    exec_ms_p90: int = 0
    exec_ms_p99: int = 0
    submit_to_receipt_ms_p50: int = 0
    submit_to_receipt_ms_p90: int = 0
    submit_to_receipt_ms_p99: int = 0


class TopOpportunity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opportunity_id: str
    route_id: str = ""
    strategy_id: str = "flashloan_atomic"
    expected_profit_after_costs_wei: str = "0"
    expected_profit_after_gas_usd_micro: int = 0
    expected_profit_usd_micro: int = 0
    send_mode_hint: str = ""
    competition: Literal["low", "medium", "high"] = "medium"
    venue_tags: List[str] = Field(default_factory=list)
    why: List[str] = Field(default_factory=list)


class LastOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    ok: bool
    reward_scaled_ppm: int = 0
    realized_after_gas_usd_micro: int = 0


class ReferenceAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal: Optional[ProposalOutput] = None
    quality: Literal["best_known", "none"] = "none"


class EpisodeContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: str
    replay_event_id: str = ""
    decision_id: str
    chain: str
    chain_id: int
    block_number: int
    opportunity_id: str
    route_id: str = ""
    v1_focus: str = "flashloan_atomic"
    regime_state: str = "unknown"
    risk_state: str = "normal"
    risk_caps: RiskCaps = Field(default_factory=RiskCaps)
    breakers: BreakerState = Field(default_factory=BreakerState)
    latency: LatencyProfile = Field(default_factory=LatencyProfile)
    last_outcomes: List[LastOutcome] = Field(default_factory=list)
    top_opportunities: List[TopOpportunity] = Field(default_factory=list)
    controls: Dict[str, Any] = Field(default_factory=dict)
    wealth_goal: Dict[str, Any] = Field(default_factory=dict)
    capital_demand: CapitalDemand = Field(default_factory=CapitalDemand)
    reward_trace: Dict[str, Any] = Field(default_factory=dict)
    execution_summary: Dict[str, Any] = Field(default_factory=dict)


class EpisodeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: EpisodeContext
    reference: ReferenceAction = Field(default_factory=ReferenceAction)


class ReplayBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_hash: str = ""
    chain: str
    chain_id: int
    block_number: int
    opportunity_id: str
    route_id: str = ""
    decision_id: str
    created_at_ms: int
    status: Literal["draft", "dry_run", "submitted", "settled", "failed"] = "draft"
    audit_hash: str = ""
    tx_hash: str = ""
    runtime: Dict[str, Any] = Field(default_factory=dict)
    controls: Dict[str, Any] = Field(default_factory=dict)
    wealth_goal: Dict[str, Any] = Field(default_factory=dict)
    capital_demand: CapitalDemand = Field(default_factory=CapitalDemand)
    opportunities: List[TopOpportunity] = Field(default_factory=list)
    execution: Dict[str, Any] = Field(default_factory=dict)
    receipt: Dict[str, Any] = Field(default_factory=dict)
    decoded_receipt: Dict[str, Any] = Field(default_factory=dict)
    reward_trace: Dict[str, Any] = Field(default_factory=dict)


class ScoreComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    reward_ppm: int
    passed: bool
    reason: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)


class ScoreResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: str
    proposal_valid: bool
    total_reward_ppm: int
    components: List[ScoreComponent] = Field(default_factory=list)
    proposal: Optional[ProposalOutput] = None
