import { apiGet, apiPost, type JsonObject } from "./client";
import type {
  CommandCenterSnapshot,
  ExplainResponse,
  FundHealthSummary,
  LaunchSummary,
  SummaryReadContract,
} from "../commandCenter/types";

export type BackendCapability =
  | "none"
  | "admin:read"
  | "admin:write"
  | "execute"
  | "governance"
  | "treasury:write"
  | "evolution:write";

export type CanonicalReadContract = {
  method: "GET";
  path: string;
  capability: BackendCapability;
  truthFamily: string;
  readModel: string;
};

export type MutationAuthority = "control" | "execution" | "capital_write" | "chain_control";

export type MutationContract = {
  method: "POST";
  path: string;
  capability: Exclude<BackendCapability, "none">;
  authority: MutationAuthority;
  requiresLiveAuthority: boolean;
};

export type CanonicalProjection<T extends JsonObject = JsonObject> = T & {
  summaryContract?: SummaryReadContract;
};

export type EngineStateResponse = CanonicalProjection<{
  ok?: boolean;
  items?: JsonObject[];
  capabilities?: JsonObject;
  summary?: { engines?: JsonObject[] };
}>;

export type LaunchFamilyDetailResponse = CanonicalProjection<JsonObject>;
export type XaiLatestResponse = CanonicalProjection<{ ok?: boolean; items?: JsonObject[]; storage?: JsonObject }>;
export type XaiDecisionResponse = CanonicalProjection<{ ok?: boolean; item?: JsonObject | null; storage?: JsonObject }>;
export type ReliabilityStateResponse = CanonicalProjection<{ ok?: boolean; state?: JsonObject }>;
export type KdsStateResponse = CanonicalProjection<{ ok?: boolean; state?: JsonObject }>;
export type RiskLiveStateResponse = CanonicalProjection<JsonObject>;
export type ExecutionQualityResponse = CanonicalProjection<JsonObject>;
export type ServiceHealthResponse = CanonicalProjection<JsonObject>;
export type CapitalExplainResponse = CanonicalProjection<JsonObject>;
export type WealthGoalResponse = CanonicalProjection<JsonObject>;
export type CommandCenterAuditResponse = CanonicalProjection<JsonObject>;
export type SpreadOpportunitiesResponse = CanonicalProjection<{
  ok?: boolean;
  opps?: JsonObject[];
  items?: JsonObject[];
}>;

export const CANONICAL_READ_CONTRACTS = {
  commandCenterSnapshot: {
    method: "GET",
    path: "/api/commandcenter/snapshot",
    capability: "none",
    truthFamily: "command_center",
    readModel: "command_center_summary_projection_v1",
  },
  commandCenterAuditTail: {
    method: "GET",
    path: "/api/commandcenter/audit/tail",
    capability: "none",
    truthFamily: "command_center_audit",
    readModel: "command_center_audit_projection_v1",
  },
  commandCenterExplain: {
    method: "GET",
    path: "/api/commandcenter/explain",
    capability: "none",
    truthFamily: "command_center_explain",
    readModel: "command_center_explain_projection_v1",
  },
  enginesState: {
    method: "GET",
    path: "/api/engines/state",
    capability: "none",
    truthFamily: "engine_state",
    readModel: "engine_state_projection_v1",
  },
  fundSummary: {
    method: "GET",
    path: "/api/fund/summary",
    capability: "none",
    truthFamily: "fund",
    readModel: "fund_summary_projection_v1",
  },
  spreadOpportunities: {
    method: "GET",
    path: "/api/spread/opportunities",
    capability: "none",
    truthFamily: "spread_opportunities",
    readModel: "spread_opportunities_projection_v1",
  },
  launchState: {
    method: "GET",
    path: "/api/launch/state",
    capability: "none",
    truthFamily: "launch",
    readModel: "launch_summary_projection_v1",
  },
  launchFamilyDetail: {
    method: "GET",
    path: "/api/launch/family/{family}",
    capability: "none",
    truthFamily: "launch_family",
    readModel: "launch_family_projection_v1",
  },
  xaiLatest: {
    method: "GET",
    path: "/api/xai/latest",
    capability: "none",
    truthFamily: "xai_latest",
    readModel: "xai_latest_projection_v1",
  },
  xaiDecision: {
    method: "GET",
    path: "/api/xai/decision/{decision_id}",
    capability: "none",
    truthFamily: "xai_decision",
    readModel: "xai_decision_projection_v1",
  },
  reliabilityState: {
    method: "GET",
    path: "/api/reliability/state",
    capability: "none",
    truthFamily: "reliability_state",
    readModel: "reliability_state_projection_v1",
  },
  kdsState: {
    method: "GET",
    path: "/api/kds/state",
    capability: "none",
    truthFamily: "kds_state",
    readModel: "kds_state_projection_v1",
  },
  riskLiveState: {
    method: "GET",
    path: "/api/risk/live-state",
    capability: "none",
    truthFamily: "risk_live_state",
    readModel: "risk_live_state_projection_v1",
  },
  executionQuality: {
    method: "GET",
    path: "/api/system/execution/quality",
    capability: "none",
    truthFamily: "execution_quality",
    readModel: "execution_quality_projection_v1",
  },
  serviceHealth: {
    method: "GET",
    path: "/api/system/services",
    capability: "none",
    truthFamily: "service_health",
    readModel: "service_health_projection_v1",
  },
  capitalExplain: {
    method: "GET",
    path: "/api/system/capital/explain",
    capability: "none",
    truthFamily: "capital_explain",
    readModel: "capital_explain_projection_v1",
  },
  wealthGoal: {
    method: "GET",
    path: "/api/wealth/goal",
    capability: "none",
    truthFamily: "wealth_goal",
    readModel: "wealth_goal_projection_v1",
  },
} as const satisfies Record<string, CanonicalReadContract>;

export const MUTATION_CONTRACTS = {
  commandCenterControl: { method: "POST", path: "/api/commandcenter/control", capability: "admin:write", authority: "control", requiresLiveAuthority: false },
  runtimeStart: { method: "POST", path: "/api/runtime/start", capability: "admin:write", authority: "control", requiresLiveAuthority: false },
  runtimeStop: { method: "POST", path: "/api/runtime/stop", capability: "admin:write", authority: "control", requiresLiveAuthority: false },
  settings: { method: "POST", path: "/api/settings", capability: "admin:write", authority: "control", requiresLiveAuthority: false },
  safety: { method: "POST", path: "/api/safety", capability: "admin:write", authority: "control", requiresLiveAuthority: false },
  tradeOpportunity: { method: "POST", path: "/api/opportunities/trade", capability: "execute", authority: "execution", requiresLiveAuthority: true },
  simulateOpportunity: { method: "POST", path: "/api/opportunities/simulate", capability: "admin:write", authority: "control", requiresLiveAuthority: false },
  withdrawExecute: { method: "POST", path: "/api/withdraw/execute", capability: "admin:write", authority: "capital_write", requiresLiveAuthority: true },
  withdrawAllExecute: { method: "POST", path: "/api/withdraw/all/execute", capability: "admin:write", authority: "capital_write", requiresLiveAuthority: true },
  convertWithdrawExecute: { method: "POST", path: "/api/withdraw/convert/execute", capability: "admin:write", authority: "capital_write", requiresLiveAuthority: true },
  rpcPreferences: { method: "POST", path: "/api/system/rpc/preferences", capability: "admin:write", authority: "control", requiresLiveAuthority: false },
  applyPreset: { method: "POST", path: "/api/presets/apply", capability: "admin:write", authority: "control", requiresLiveAuthority: false },
  selectChain: { method: "POST", path: "/api/multichain/select", capability: "admin:write", authority: "chain_control", requiresLiveAuthority: false },
  metaApply: { method: "POST", path: "/api/meta/apply", capability: "admin:write", authority: "control", requiresLiveAuthority: false },
  wealthGoal: { method: "POST", path: "/api/wealth/goal", capability: "admin:write", authority: "control", requiresLiveAuthority: false },
  launchMode: { method: "POST", path: "/api/launch/mode", capability: "admin:write", authority: "control", requiresLiveAuthority: false },
  launchEnableNext: { method: "POST", path: "/api/launch/enable-next", capability: "admin:write", authority: "control", requiresLiveAuthority: false },
  launchPauseFamily: { method: "POST", path: "/api/launch/pause-family", capability: "admin:write", authority: "control", requiresLiveAuthority: false },
  launchRevertFamily: { method: "POST", path: "/api/launch/revert-family", capability: "admin:write", authority: "control", requiresLiveAuthority: false },
  launchQuarantineFamily: { method: "POST", path: "/api/launch/quarantine-family", capability: "admin:write", authority: "control", requiresLiveAuthority: false },
} as const satisfies Record<string, MutationContract>;

function headers(adminKey?: string): Record<string, string> {
  return adminKey ? { "X-Admin-Key": adminKey } : {};
}

function requireSummaryContract<T extends object>(
  payload: T,
  contract: CanonicalReadContract,
): T & { summaryContract: SummaryReadContract } {
  const summaryContract = (payload as { summaryContract?: SummaryReadContract }).summaryContract;
  if (!summaryContract) {
    throw new Error(`canonical_contract_missing:${contract.path}`);
  }
  if (summaryContract.truthFamily !== contract.truthFamily) {
    throw new Error(`canonical_truth_family_mismatch:${contract.path}`);
  }
  if (summaryContract.readModel !== contract.readModel) {
    throw new Error(`canonical_read_model_mismatch:${contract.path}`);
  }
  return { ...payload, summaryContract } as T & { summaryContract: SummaryReadContract };
}

export async function canonicalCommandCenterSnapshot(baseUrl: string, adminKey?: string): Promise<CommandCenterSnapshot> {
  return requireSummaryContract(
    (await apiGet(baseUrl, CANONICAL_READ_CONTRACTS.commandCenterSnapshot.path, headers(adminKey))) as CommandCenterSnapshot,
    CANONICAL_READ_CONTRACTS.commandCenterSnapshot,
  );
}

export async function canonicalCommandCenterAuditTail(baseUrl: string, limit = 200, adminKey?: string): Promise<CommandCenterAuditResponse> {
  const path = `${CANONICAL_READ_CONTRACTS.commandCenterAuditTail.path}?limit=${encodeURIComponent(String(limit))}`;
  return requireSummaryContract(
    (await apiGet(baseUrl, path, headers(adminKey))) as CommandCenterAuditResponse,
    CANONICAL_READ_CONTRACTS.commandCenterAuditTail,
  );
}

export async function canonicalCommandCenterExplain(baseUrl: string, adminKey?: string): Promise<ExplainResponse> {
  return requireSummaryContract(
    (await apiGet(baseUrl, CANONICAL_READ_CONTRACTS.commandCenterExplain.path, headers(adminKey))) as ExplainResponse,
    CANONICAL_READ_CONTRACTS.commandCenterExplain,
  );
}

export async function canonicalEngineState(baseUrl: string, adminKey?: string): Promise<EngineStateResponse> {
  return requireSummaryContract(
    (await apiGet(baseUrl, CANONICAL_READ_CONTRACTS.enginesState.path, headers(adminKey))) as EngineStateResponse,
    CANONICAL_READ_CONTRACTS.enginesState,
  );
}

export async function canonicalFundSummary(baseUrl: string, adminKey?: string): Promise<FundHealthSummary> {
  return requireSummaryContract(
    (await apiGet(baseUrl, CANONICAL_READ_CONTRACTS.fundSummary.path, headers(adminKey))) as FundHealthSummary,
    CANONICAL_READ_CONTRACTS.fundSummary,
  );
}

export async function canonicalSpreadOpportunities(baseUrl: string, adminKey?: string): Promise<SpreadOpportunitiesResponse> {
  return requireSummaryContract(
    (await apiGet(baseUrl, CANONICAL_READ_CONTRACTS.spreadOpportunities.path, headers(adminKey))) as SpreadOpportunitiesResponse,
    CANONICAL_READ_CONTRACTS.spreadOpportunities,
  );
}

export async function canonicalLaunchState(baseUrl: string, adminKey?: string): Promise<LaunchSummary> {
  return requireSummaryContract(
    (await apiGet(baseUrl, CANONICAL_READ_CONTRACTS.launchState.path, headers(adminKey))) as LaunchSummary,
    CANONICAL_READ_CONTRACTS.launchState,
  );
}

export async function canonicalLaunchFamilyDetail(baseUrl: string, family: string, adminKey?: string): Promise<LaunchFamilyDetailResponse> {
  const path = `${CANONICAL_READ_CONTRACTS.launchFamilyDetail.path.replace("{family}", encodeURIComponent(family))}`;
  return requireSummaryContract(
    (await apiGet(baseUrl, path, headers(adminKey))) as LaunchFamilyDetailResponse,
    CANONICAL_READ_CONTRACTS.launchFamilyDetail,
  );
}

export async function canonicalXaiLatest(baseUrl: string, limit = 50, adminKey?: string): Promise<XaiLatestResponse> {
  return requireSummaryContract(
    (await apiGet(baseUrl, `${CANONICAL_READ_CONTRACTS.xaiLatest.path}?limit=${encodeURIComponent(String(limit))}`, headers(adminKey))) as XaiLatestResponse,
    CANONICAL_READ_CONTRACTS.xaiLatest,
  );
}

export async function canonicalXaiDecision(baseUrl: string, decisionId: string, adminKey?: string): Promise<XaiDecisionResponse> {
  const path = CANONICAL_READ_CONTRACTS.xaiDecision.path.replace("{decision_id}", encodeURIComponent(decisionId));
  return requireSummaryContract(
    (await apiGet(baseUrl, path, headers(adminKey))) as XaiDecisionResponse,
    CANONICAL_READ_CONTRACTS.xaiDecision,
  );
}

export async function canonicalReliabilityState(baseUrl: string, adminKey?: string): Promise<ReliabilityStateResponse> {
  return requireSummaryContract(
    (await apiGet(baseUrl, CANONICAL_READ_CONTRACTS.reliabilityState.path, headers(adminKey))) as ReliabilityStateResponse,
    CANONICAL_READ_CONTRACTS.reliabilityState,
  );
}

export async function canonicalKdsState(baseUrl: string, adminKey?: string): Promise<KdsStateResponse> {
  return requireSummaryContract(
    (await apiGet(baseUrl, CANONICAL_READ_CONTRACTS.kdsState.path, headers(adminKey))) as KdsStateResponse,
    CANONICAL_READ_CONTRACTS.kdsState,
  );
}

export async function canonicalRiskLiveState(baseUrl: string, adminKey?: string): Promise<RiskLiveStateResponse> {
  return requireSummaryContract(
    (await apiGet(baseUrl, CANONICAL_READ_CONTRACTS.riskLiveState.path, headers(adminKey))) as RiskLiveStateResponse,
    CANONICAL_READ_CONTRACTS.riskLiveState,
  );
}

export async function canonicalExecutionQuality(baseUrl: string, adminKey?: string): Promise<ExecutionQualityResponse> {
  return requireSummaryContract(
    (await apiGet(baseUrl, CANONICAL_READ_CONTRACTS.executionQuality.path, headers(adminKey))) as ExecutionQualityResponse,
    CANONICAL_READ_CONTRACTS.executionQuality,
  );
}

export async function canonicalServiceHealth(baseUrl: string, adminKey?: string): Promise<ServiceHealthResponse> {
  return requireSummaryContract(
    (await apiGet(baseUrl, CANONICAL_READ_CONTRACTS.serviceHealth.path, headers(adminKey))) as ServiceHealthResponse,
    CANONICAL_READ_CONTRACTS.serviceHealth,
  );
}

export async function canonicalCapitalExplain(baseUrl: string, adminKey?: string): Promise<CapitalExplainResponse> {
  return requireSummaryContract(
    (await apiGet(baseUrl, CANONICAL_READ_CONTRACTS.capitalExplain.path, headers(adminKey))) as CapitalExplainResponse,
    CANONICAL_READ_CONTRACTS.capitalExplain,
  );
}

export async function canonicalWealthGoal(baseUrl: string, adminKey?: string): Promise<WealthGoalResponse> {
  return requireSummaryContract(
    (await apiGet(baseUrl, CANONICAL_READ_CONTRACTS.wealthGoal.path, headers(adminKey))) as WealthGoalResponse,
    CANONICAL_READ_CONTRACTS.wealthGoal,
  );
}

export async function canonicalCommandCenterControl(
  baseUrl: string,
  patch: JsonObject,
  reason: string,
  adminKey: string,
): Promise<JsonObject> {
  return (await apiPost(baseUrl, MUTATION_CONTRACTS.commandCenterControl.path, { patch, reason }, headers(adminKey))) as JsonObject;
}

export async function canonicalSetLaunchMode(baseUrl: string, mode: string, adminKey: string): Promise<JsonObject> {
  return (await apiPost(baseUrl, MUTATION_CONTRACTS.launchMode.path, { mode }, headers(adminKey))) as JsonObject;
}

export async function canonicalSetWealthGoal(baseUrl: string, patch: JsonObject, adminKey: string): Promise<JsonObject> {
  return (await apiPost(baseUrl, MUTATION_CONTRACTS.wealthGoal.path, patch, headers(adminKey))) as JsonObject;
}

export async function canonicalTradeOpportunity(
  baseUrl: string,
  id: string,
  adminKey: string,
  amountInOverride?: string,
): Promise<JsonObject> {
  const body: JsonObject = { id };
  if (amountInOverride !== undefined) body.amount_in_override = String(amountInOverride);
  return (await apiPost(baseUrl, MUTATION_CONTRACTS.tradeOpportunity.path, body, headers(adminKey))) as JsonObject;
}
