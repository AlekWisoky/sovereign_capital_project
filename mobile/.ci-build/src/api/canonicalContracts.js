"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.canonicalTradeOpportunity = exports.canonicalSetWealthGoal = exports.canonicalSetLaunchMode = exports.canonicalCommandCenterControl = exports.canonicalWealthGoal = exports.canonicalCapitalExplain = exports.canonicalServiceHealth = exports.canonicalExecutionQuality = exports.canonicalRiskLiveState = exports.canonicalKdsState = exports.canonicalReliabilityState = exports.canonicalXaiDecision = exports.canonicalXaiLatest = exports.canonicalLaunchFamilyDetail = exports.canonicalLaunchState = exports.canonicalSpreadOpportunities = exports.canonicalFundSummary = exports.canonicalEngineState = exports.canonicalCommandCenterExplain = exports.canonicalCommandCenterAuditTail = exports.canonicalCommandCenterSnapshot = exports.MUTATION_CONTRACTS = exports.CANONICAL_READ_CONTRACTS = void 0;
const client_1 = require("./client");
exports.CANONICAL_READ_CONTRACTS = {
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
};
exports.MUTATION_CONTRACTS = {
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
};
function headers(adminKey) {
    return adminKey ? { "X-Admin-Key": adminKey } : {};
}
function requireSummaryContract(payload, contract) {
    const summaryContract = payload.summaryContract;
    if (!summaryContract) {
        throw new Error(`canonical_contract_missing:${contract.path}`);
    }
    if (summaryContract.truthFamily !== contract.truthFamily) {
        throw new Error(`canonical_truth_family_mismatch:${contract.path}`);
    }
    if (summaryContract.readModel !== contract.readModel) {
        throw new Error(`canonical_read_model_mismatch:${contract.path}`);
    }
    return { ...payload, summaryContract };
}
async function canonicalCommandCenterSnapshot(baseUrl, adminKey) {
    return requireSummaryContract((await (0, client_1.apiGet)(baseUrl, exports.CANONICAL_READ_CONTRACTS.commandCenterSnapshot.path, headers(adminKey))), exports.CANONICAL_READ_CONTRACTS.commandCenterSnapshot);
}
exports.canonicalCommandCenterSnapshot = canonicalCommandCenterSnapshot;
async function canonicalCommandCenterAuditTail(baseUrl, limit = 200, adminKey) {
    const path = `${exports.CANONICAL_READ_CONTRACTS.commandCenterAuditTail.path}?limit=${encodeURIComponent(String(limit))}`;
    return requireSummaryContract((await (0, client_1.apiGet)(baseUrl, path, headers(adminKey))), exports.CANONICAL_READ_CONTRACTS.commandCenterAuditTail);
}
exports.canonicalCommandCenterAuditTail = canonicalCommandCenterAuditTail;
async function canonicalCommandCenterExplain(baseUrl, adminKey) {
    return requireSummaryContract((await (0, client_1.apiGet)(baseUrl, exports.CANONICAL_READ_CONTRACTS.commandCenterExplain.path, headers(adminKey))), exports.CANONICAL_READ_CONTRACTS.commandCenterExplain);
}
exports.canonicalCommandCenterExplain = canonicalCommandCenterExplain;
async function canonicalEngineState(baseUrl, adminKey) {
    return requireSummaryContract((await (0, client_1.apiGet)(baseUrl, exports.CANONICAL_READ_CONTRACTS.enginesState.path, headers(adminKey))), exports.CANONICAL_READ_CONTRACTS.enginesState);
}
exports.canonicalEngineState = canonicalEngineState;
async function canonicalFundSummary(baseUrl, adminKey) {
    return requireSummaryContract((await (0, client_1.apiGet)(baseUrl, exports.CANONICAL_READ_CONTRACTS.fundSummary.path, headers(adminKey))), exports.CANONICAL_READ_CONTRACTS.fundSummary);
}
exports.canonicalFundSummary = canonicalFundSummary;
async function canonicalSpreadOpportunities(baseUrl, adminKey) {
    return requireSummaryContract((await (0, client_1.apiGet)(baseUrl, exports.CANONICAL_READ_CONTRACTS.spreadOpportunities.path, headers(adminKey))), exports.CANONICAL_READ_CONTRACTS.spreadOpportunities);
}
exports.canonicalSpreadOpportunities = canonicalSpreadOpportunities;
async function canonicalLaunchState(baseUrl, adminKey) {
    return requireSummaryContract((await (0, client_1.apiGet)(baseUrl, exports.CANONICAL_READ_CONTRACTS.launchState.path, headers(adminKey))), exports.CANONICAL_READ_CONTRACTS.launchState);
}
exports.canonicalLaunchState = canonicalLaunchState;
async function canonicalLaunchFamilyDetail(baseUrl, family, adminKey) {
    const path = `${exports.CANONICAL_READ_CONTRACTS.launchFamilyDetail.path.replace("{family}", encodeURIComponent(family))}`;
    return requireSummaryContract((await (0, client_1.apiGet)(baseUrl, path, headers(adminKey))), exports.CANONICAL_READ_CONTRACTS.launchFamilyDetail);
}
exports.canonicalLaunchFamilyDetail = canonicalLaunchFamilyDetail;
async function canonicalXaiLatest(baseUrl, limit = 50, adminKey) {
    return requireSummaryContract((await (0, client_1.apiGet)(baseUrl, `${exports.CANONICAL_READ_CONTRACTS.xaiLatest.path}?limit=${encodeURIComponent(String(limit))}`, headers(adminKey))), exports.CANONICAL_READ_CONTRACTS.xaiLatest);
}
exports.canonicalXaiLatest = canonicalXaiLatest;
async function canonicalXaiDecision(baseUrl, decisionId, adminKey) {
    const path = exports.CANONICAL_READ_CONTRACTS.xaiDecision.path.replace("{decision_id}", encodeURIComponent(decisionId));
    return requireSummaryContract((await (0, client_1.apiGet)(baseUrl, path, headers(adminKey))), exports.CANONICAL_READ_CONTRACTS.xaiDecision);
}
exports.canonicalXaiDecision = canonicalXaiDecision;
async function canonicalReliabilityState(baseUrl, adminKey) {
    return requireSummaryContract((await (0, client_1.apiGet)(baseUrl, exports.CANONICAL_READ_CONTRACTS.reliabilityState.path, headers(adminKey))), exports.CANONICAL_READ_CONTRACTS.reliabilityState);
}
exports.canonicalReliabilityState = canonicalReliabilityState;
async function canonicalKdsState(baseUrl, adminKey) {
    return requireSummaryContract((await (0, client_1.apiGet)(baseUrl, exports.CANONICAL_READ_CONTRACTS.kdsState.path, headers(adminKey))), exports.CANONICAL_READ_CONTRACTS.kdsState);
}
exports.canonicalKdsState = canonicalKdsState;
async function canonicalRiskLiveState(baseUrl, adminKey) {
    return requireSummaryContract((await (0, client_1.apiGet)(baseUrl, exports.CANONICAL_READ_CONTRACTS.riskLiveState.path, headers(adminKey))), exports.CANONICAL_READ_CONTRACTS.riskLiveState);
}
exports.canonicalRiskLiveState = canonicalRiskLiveState;
async function canonicalExecutionQuality(baseUrl, adminKey) {
    return requireSummaryContract((await (0, client_1.apiGet)(baseUrl, exports.CANONICAL_READ_CONTRACTS.executionQuality.path, headers(adminKey))), exports.CANONICAL_READ_CONTRACTS.executionQuality);
}
exports.canonicalExecutionQuality = canonicalExecutionQuality;
async function canonicalServiceHealth(baseUrl, adminKey) {
    return requireSummaryContract((await (0, client_1.apiGet)(baseUrl, exports.CANONICAL_READ_CONTRACTS.serviceHealth.path, headers(adminKey))), exports.CANONICAL_READ_CONTRACTS.serviceHealth);
}
exports.canonicalServiceHealth = canonicalServiceHealth;
async function canonicalCapitalExplain(baseUrl, adminKey) {
    return requireSummaryContract((await (0, client_1.apiGet)(baseUrl, exports.CANONICAL_READ_CONTRACTS.capitalExplain.path, headers(adminKey))), exports.CANONICAL_READ_CONTRACTS.capitalExplain);
}
exports.canonicalCapitalExplain = canonicalCapitalExplain;
async function canonicalWealthGoal(baseUrl, adminKey) {
    return requireSummaryContract((await (0, client_1.apiGet)(baseUrl, exports.CANONICAL_READ_CONTRACTS.wealthGoal.path, headers(adminKey))), exports.CANONICAL_READ_CONTRACTS.wealthGoal);
}
exports.canonicalWealthGoal = canonicalWealthGoal;
async function canonicalCommandCenterControl(baseUrl, patch, reason, adminKey) {
    return (await (0, client_1.apiPost)(baseUrl, exports.MUTATION_CONTRACTS.commandCenterControl.path, { patch, reason }, headers(adminKey)));
}
exports.canonicalCommandCenterControl = canonicalCommandCenterControl;
async function canonicalSetLaunchMode(baseUrl, mode, adminKey) {
    return (await (0, client_1.apiPost)(baseUrl, exports.MUTATION_CONTRACTS.launchMode.path, { mode }, headers(adminKey)));
}
exports.canonicalSetLaunchMode = canonicalSetLaunchMode;
async function canonicalSetWealthGoal(baseUrl, patch, adminKey) {
    return (await (0, client_1.apiPost)(baseUrl, exports.MUTATION_CONTRACTS.wealthGoal.path, patch, headers(adminKey)));
}
exports.canonicalSetWealthGoal = canonicalSetWealthGoal;
async function canonicalTradeOpportunity(baseUrl, id, adminKey, amountInOverride) {
    const body = { id };
    if (amountInOverride !== undefined)
        body.amount_in_override = String(amountInOverride);
    return (await (0, client_1.apiPost)(baseUrl, exports.MUTATION_CONTRACTS.tradeOpportunity.path, body, headers(adminKey)));
}
exports.canonicalTradeOpportunity = canonicalTradeOpportunity;
