"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const node_fs_1 = require("node:fs");
const canonicalContracts_1 = require("../src/api/canonicalContracts");
const canonical_1 = require("../src/api/canonical");
const reconciliation_1 = require("../src/api/reconciliation");
const mutationGuard_1 = require("../src/api/mutationGuard");
function installFetch(response) {
    const calls = [];
    const previous = globalThis.fetch;
    globalThis.fetch = (async (input, init) => {
        calls.push({ url: String(input), init });
        return {
            ok: true,
            status: 200,
            json: async () => response,
        };
    });
    return { calls, restore: () => { globalThis.fetch = previous; } };
}
const canonical = (truthFamily, readModel) => ({
    ok: true,
    summaryContract: {
        contractVersion: "canonical_summary_read_contract_v1",
        truthFamily,
        readModel,
    },
});
(0, node_test_1.default)("canonical read adapters preserve the existing summary contract and exact endpoint", async () => {
    const response = canonical(canonicalContracts_1.CANONICAL_READ_CONTRACTS.commandCenterAuditTail.truthFamily, canonicalContracts_1.CANONICAL_READ_CONTRACTS.commandCenterAuditTail.readModel);
    const { calls, restore } = installFetch(response);
    try {
        await (0, canonicalContracts_1.canonicalCommandCenterAuditTail)("https://api.example.test", 7, "secret");
        strict_1.default.equal(calls.length, 1);
        strict_1.default.equal(calls[0].url, "https://api.example.test/api/commandcenter/audit/tail?limit=7");
        strict_1.default.equal(calls[0].init?.method, undefined);
        strict_1.default.deepEqual((calls[0].init?.headers ?? {}), { "X-Admin-Key": "secret" });
    }
    finally {
        restore();
    }
});
(0, node_test_1.default)("parameterized canonical adapters encode path parameters and validate read-model identity", async () => {
    const response = canonical(canonicalContracts_1.CANONICAL_READ_CONTRACTS.launchFamilyDetail.truthFamily, canonicalContracts_1.CANONICAL_READ_CONTRACTS.launchFamilyDetail.readModel);
    const { calls, restore } = installFetch(response);
    try {
        await (0, canonicalContracts_1.canonicalLaunchFamilyDetail)("https://api.example.test", "family/a", "secret");
        strict_1.default.equal(calls[0].url, "https://api.example.test/api/launch/family/family%2Fa");
    }
    finally {
        restore();
    }
});
(0, node_test_1.default)("canonical spread-opportunity adapter enforces the declared projection identity", async () => {
    const response = {
        ...canonical(canonicalContracts_1.CANONICAL_READ_CONTRACTS.spreadOpportunities.truthFamily, canonicalContracts_1.CANONICAL_READ_CONTRACTS.spreadOpportunities.readModel),
        items: [],
    };
    const { calls, restore } = installFetch(response);
    try {
        const out = await (0, canonicalContracts_1.canonicalSpreadOpportunities)("https://api.example.test", "secret");
        strict_1.default.deepEqual(out.items, []);
        strict_1.default.equal(calls[0].url, "https://api.example.test/api/spread/opportunities");
        strict_1.default.equal(calls[0].init?.method, undefined);
    }
    finally {
        restore();
    }
});
(0, node_test_1.default)("canonical adapter rejects a mismatched backend truth family", async () => {
    const response = canonical("wrong_family", canonicalContracts_1.CANONICAL_READ_CONTRACTS.xaiDecision.readModel);
    const { restore } = installFetch(response);
    await strict_1.default.rejects(() => (0, canonicalContracts_1.canonicalXaiDecision)("https://api.example.test", "decision/1"), /canonical_truth_family_mismatch/);
    restore();
});
(0, node_test_1.default)("mutation contracts encode backend capability and preserve admin-key authorization", async () => {
    strict_1.default.equal(canonicalContracts_1.MUTATION_CONTRACTS.commandCenterControl.method, "POST");
    strict_1.default.equal(canonicalContracts_1.MUTATION_CONTRACTS.commandCenterControl.path, "/api/commandcenter/control");
    strict_1.default.equal(canonicalContracts_1.MUTATION_CONTRACTS.commandCenterControl.capability, "admin:write");
    strict_1.default.equal(canonicalContracts_1.MUTATION_CONTRACTS.launchMode.capability, "admin:write");
    strict_1.default.equal(canonicalContracts_1.MUTATION_CONTRACTS.tradeOpportunity.capability, "execute");
    strict_1.default.equal(canonicalContracts_1.MUTATION_CONTRACTS.tradeOpportunity.authority, "execution");
    strict_1.default.equal(canonicalContracts_1.MUTATION_CONTRACTS.tradeOpportunity.requiresLiveAuthority, true);
    strict_1.default.equal(canonicalContracts_1.MUTATION_CONTRACTS.withdrawExecute.capability, "admin:write");
    strict_1.default.equal(canonicalContracts_1.MUTATION_CONTRACTS.withdrawExecute.authority, "capital_write");
    strict_1.default.equal(canonicalContracts_1.MUTATION_CONTRACTS.withdrawExecute.requiresLiveAuthority, true);
    const response = { ok: true };
    const { calls, restore } = installFetch(response);
    try {
        await (0, canonicalContracts_1.canonicalCommandCenterControl)("https://api.example.test", { auto_trading: false }, "operator-confirmed", "secret");
        strict_1.default.equal(calls[0].url, "https://api.example.test/api/commandcenter/control");
        strict_1.default.equal(calls[0].init?.method, "POST");
        strict_1.default.equal(calls[0].init?.headers && (calls[0].init?.headers)["X-Admin-Key"], "secret");
        strict_1.default.deepEqual(JSON.parse(String(calls[0].init?.body)), {
            patch: { auto_trading: false },
            reason: "operator-confirmed",
        });
    }
    finally {
        restore();
    }
});
(0, node_test_1.default)("canonical engine adapter uses GET and its declared engine projection identity", async () => {
    const response = {
        ...canonical(canonicalContracts_1.CANONICAL_READ_CONTRACTS.enginesState.truthFamily, canonicalContracts_1.CANONICAL_READ_CONTRACTS.enginesState.readModel),
        summary: { engines: [] },
    };
    const { calls, restore } = installFetch(response);
    try {
        const out = await (0, canonicalContracts_1.canonicalEngineState)("https://api.example.test");
        strict_1.default.equal(out.summaryContract?.truthFamily, "engine_state");
        strict_1.default.equal(calls[0].url, "https://api.example.test/api/engines/state");
        strict_1.default.equal(calls[0].init?.method, undefined);
    }
    finally {
        restore();
    }
});
(0, node_test_1.default)("command-center provider routes canonical reads through the typed contract layer", () => {
    const source = (0, node_fs_1.readFileSync)("src/commandCenter/provider.ts", "utf8");
    strict_1.default.match(source, /canonicalCommandCenterSnapshot/);
    strict_1.default.match(source, /canonicalEngineState/);
    strict_1.default.match(source, /canonicalFundSummary/);
    strict_1.default.match(source, /canonicalExecutionQuality/);
    strict_1.default.match(source, /canonicalRiskLiveState/);
    strict_1.default.match(source, /canonicalServiceHealth/);
    strict_1.default.match(source, /canonicalCommandCenterControl/);
    strict_1.default.doesNotMatch(source, /apiGet\(baseUrl,\s*["']\/api\/(commandcenter\/snapshot|engines\/state|fund\/summary|system\/execution\/quality|risk\/live-state|system\/services)/);
});
(0, node_test_1.default)("decision adapter preserves one canonical lifecycle lineage", async () => {
    const response = {
        ...canonical(canonicalContracts_1.CANONICAL_READ_CONTRACTS.xaiDecision.truthFamily, canonicalContracts_1.CANONICAL_READ_CONTRACTS.xaiDecision.readModel),
        item: {
            decision_id: "dec-1",
            admission_allowed: true,
            admission_reason_codes: [],
            sizing_id: "size-1",
            required_capital_usd: 25,
            execution_id: "exec-1",
            receipt_id: "rcpt-1",
            tx_hash: "0xabc",
            outcome_id: "out-1",
            settlement_verified: true,
            realized_net_profit_usd: 1.25,
            learning_recorded: true,
            expectation_error_usd: -0.25,
        },
    };
    const { restore } = installFetch(response);
    try {
        const out = await (0, canonical_1.getXaiDecision)("https://api.example.test", "dec-1");
        strict_1.default.equal(out.lifecycle?.decision.decisionId, "dec-1");
        strict_1.default.equal(out.lifecycle?.sizing.sizingId, "size-1");
        strict_1.default.equal(out.lifecycle?.execution.executionId, "exec-1");
        strict_1.default.equal(out.lifecycle?.receipt.receiptId, "rcpt-1");
        strict_1.default.equal(out.lifecycle?.settlement.outcomeId, "out-1");
        strict_1.default.equal(out.lifecycle?.settlement.verified, true);
        strict_1.default.equal(out.lifecycle?.learning.recorded, true);
    }
    finally {
        restore();
    }
});
// ---------------------------------------------------------------------------
// Prompt 01A contract-freeze gate.
// These tests freeze the *existing* canonical contracts. They assert only what
// the current implementation already declares; they do not invent endpoints,
// truth families, read models, authorities, or lifecycle identifiers.
// ---------------------------------------------------------------------------
(0, node_test_1.default)("canonical endpoint identity: every read contract is GET on a unique /api path", () => {
    const entries = Object.entries(canonicalContracts_1.CANONICAL_READ_CONTRACTS);
    strict_1.default.ok(entries.length > 0);
    const seenPaths = new Set();
    const seenKeys = new Set();
    for (const [key, contract] of entries) {
        strict_1.default.equal(seenKeys.has(key), false, `duplicate canonical contract key: ${key}`);
        seenKeys.add(key);
        strict_1.default.equal(contract.method, "GET", `read contract ${key} must be GET`);
        strict_1.default.match(contract.path, /^\/api\//, `read contract ${key} must target /api`);
        strict_1.default.equal(seenPaths.has(contract.path), false, `duplicate canonical endpoint: ${contract.path}`);
        seenPaths.add(contract.path);
        strict_1.default.equal(typeof contract.truthFamily, "string");
        strict_1.default.equal(typeof contract.readModel, "string");
    }
});
(0, node_test_1.default)("canonical endpoint identity: adapters hit the declared endpoint exactly, with no fallback", async () => {
    const cases = [
        { contract: canonicalContracts_1.CANONICAL_READ_CONTRACTS.commandCenterSnapshot, call: (b) => (0, canonicalContracts_1.canonicalCommandCenterSnapshot)(b) },
        { contract: canonicalContracts_1.CANONICAL_READ_CONTRACTS.commandCenterExplain, call: (b) => (0, canonicalContracts_1.canonicalCommandCenterExplain)(b) },
        { contract: canonicalContracts_1.CANONICAL_READ_CONTRACTS.enginesState, call: (b) => (0, canonicalContracts_1.canonicalEngineState)(b) },
        { contract: canonicalContracts_1.CANONICAL_READ_CONTRACTS.fundSummary, call: (b) => (0, canonicalContracts_1.canonicalFundSummary)(b) },
        { contract: canonicalContracts_1.CANONICAL_READ_CONTRACTS.spreadOpportunities, call: (b) => (0, canonicalContracts_1.canonicalSpreadOpportunities)(b) },
        { contract: canonicalContracts_1.CANONICAL_READ_CONTRACTS.launchState, call: (b) => (0, canonicalContracts_1.canonicalLaunchState)(b) },
        { contract: canonicalContracts_1.CANONICAL_READ_CONTRACTS.reliabilityState, call: (b) => (0, canonicalContracts_1.canonicalReliabilityState)(b) },
        { contract: canonicalContracts_1.CANONICAL_READ_CONTRACTS.kdsState, call: (b) => (0, canonicalContracts_1.canonicalKdsState)(b) },
        { contract: canonicalContracts_1.CANONICAL_READ_CONTRACTS.riskLiveState, call: (b) => (0, canonicalContracts_1.canonicalRiskLiveState)(b) },
        { contract: canonicalContracts_1.CANONICAL_READ_CONTRACTS.executionQuality, call: (b) => (0, canonicalContracts_1.canonicalExecutionQuality)(b) },
        { contract: canonicalContracts_1.CANONICAL_READ_CONTRACTS.serviceHealth, call: (b) => (0, canonicalContracts_1.canonicalServiceHealth)(b) },
        { contract: canonicalContracts_1.CANONICAL_READ_CONTRACTS.capitalExplain, call: (b) => (0, canonicalContracts_1.canonicalCapitalExplain)(b) },
        { contract: canonicalContracts_1.CANONICAL_READ_CONTRACTS.wealthGoal, call: (b) => (0, canonicalContracts_1.canonicalWealthGoal)(b) },
    ];
    for (const { contract, call } of cases) {
        const { calls, restore } = installFetch(canonical(contract.truthFamily, contract.readModel));
        try {
            await call("https://api.example.test");
            strict_1.default.equal(calls.length, 1, `${contract.path} issued ${calls.length} calls`);
            strict_1.default.equal(calls[0].url, `https://api.example.test${contract.path}`);
            strict_1.default.equal(calls[0].init?.method, undefined);
        }
        finally {
            restore();
        }
    }
});
(0, node_test_1.default)("truth-family identity: a matching truth family is accepted", async () => {
    const response = {
        ...canonical(canonicalContracts_1.CANONICAL_READ_CONTRACTS.xaiLatest.truthFamily, canonicalContracts_1.CANONICAL_READ_CONTRACTS.xaiLatest.readModel),
        items: [],
    };
    const { restore } = installFetch(response);
    try {
        const out = await (0, canonicalContracts_1.canonicalXaiLatest)("https://api.example.test");
        strict_1.default.equal(out.summaryContract?.truthFamily, canonicalContracts_1.CANONICAL_READ_CONTRACTS.xaiLatest.truthFamily);
    }
    finally {
        restore();
    }
});
(0, node_test_1.default)("truth-family identity: a mismatched truth family fails closed", async () => {
    const response = canonical("not_spread_opportunities", canonicalContracts_1.CANONICAL_READ_CONTRACTS.spreadOpportunities.readModel);
    const { restore } = installFetch(response);
    try {
        await strict_1.default.rejects(() => (0, canonicalContracts_1.canonicalSpreadOpportunities)("https://api.example.test"), /canonical_truth_family_mismatch/);
    }
    finally {
        restore();
    }
});
(0, node_test_1.default)("read-model identity: a mismatched read model fails closed", async () => {
    const response = canonical(canonicalContracts_1.CANONICAL_READ_CONTRACTS.enginesState.truthFamily, "not_the_engine_projection");
    const { restore } = installFetch(response);
    try {
        await strict_1.default.rejects(() => (0, canonicalContracts_1.canonicalEngineState)("https://api.example.test"), /canonical_read_model_mismatch/);
    }
    finally {
        restore();
    }
});
(0, node_test_1.default)("read-model identity: a missing summary contract fails closed", async () => {
    const { restore } = installFetch({ ok: true });
    try {
        await strict_1.default.rejects(() => (0, canonicalContracts_1.canonicalServiceHealth)("https://api.example.test"), /canonical_contract_missing/);
    }
    finally {
        restore();
    }
});
(0, node_test_1.default)("mutation authority: existing mutation contracts preserve their authority boundaries", () => {
    const control = canonicalContracts_1.MUTATION_CONTRACTS.commandCenterControl;
    strict_1.default.equal(control.authority, "control");
    strict_1.default.equal(control.capability, "admin:write");
    strict_1.default.equal(control.requiresLiveAuthority, false);
    const execution = canonicalContracts_1.MUTATION_CONTRACTS.tradeOpportunity;
    strict_1.default.equal(execution.authority, "execution");
    strict_1.default.equal(execution.capability, "execute");
    strict_1.default.equal(execution.requiresLiveAuthority, true);
    const capitalWrite = canonicalContracts_1.MUTATION_CONTRACTS.withdrawExecute;
    strict_1.default.equal(capitalWrite.authority, "capital_write");
    strict_1.default.equal(capitalWrite.capability, "admin:write");
    strict_1.default.equal(capitalWrite.requiresLiveAuthority, true);
    const chainControl = canonicalContracts_1.MUTATION_CONTRACTS.selectChain;
    strict_1.default.equal(chainControl.authority, "chain_control");
    strict_1.default.equal(chainControl.capability, "admin:write");
    strict_1.default.equal(chainControl.requiresLiveAuthority, false);
    const allowedAuthorities = new Set(["control", "execution", "capital_write", "chain_control"]);
    const seenPaths = new Set();
    for (const [key, contract] of Object.entries(canonicalContracts_1.MUTATION_CONTRACTS)) {
        strict_1.default.equal(contract.method, "POST", `${key} must be POST`);
        strict_1.default.equal(allowedAuthorities.has(contract.authority), true, `${key} has unknown authority`);
        strict_1.default.equal(seenPaths.has(contract.path), false, `duplicate mutation endpoint: ${contract.path}`);
        seenPaths.add(contract.path);
    }
});
(0, node_test_1.default)("mutation authority: guarded mutations stay fail-closed without satisfying authority", () => {
    const base = {
        role: "operator",
        locked: false,
        adminKeyPresent: true,
        backendReachable: true,
        backendLiveAuthority: false,
        explicitConfirmation: true,
    };
    strict_1.default.deepEqual((0, mutationGuard_1.guardMutation)("execution", base), { allowed: false, reasonCode: "live_authority_disabled" });
    strict_1.default.deepEqual((0, mutationGuard_1.guardMutation)("withdrawal", base), { allowed: false, reasonCode: "live_authority_disabled" });
    strict_1.default.deepEqual((0, mutationGuard_1.guardMutation)("settings", { ...base, adminKeyPresent: false }), { allowed: false, reasonCode: "admin_key_required" });
    strict_1.default.deepEqual((0, mutationGuard_1.guardMutation)("chain_control", { ...base, explicitConfirmation: false }), { allowed: false, reasonCode: "explicit_confirmation_required" });
    strict_1.default.deepEqual((0, mutationGuard_1.guardMutation)("settings", { ...base, backendReachable: false }), { allowed: false, reasonCode: "backend_unavailable" });
    strict_1.default.deepEqual((0, mutationGuard_1.guardMutation)("settings", { ...base, role: "read_only" }), { allowed: false, reasonCode: "operator_required" });
    strict_1.default.deepEqual((0, mutationGuard_1.guardMutation)("settings", { ...base, locked: true }), { allowed: false, reasonCode: "operator_locked" });
    strict_1.default.deepEqual((0, mutationGuard_1.guardMutation)("settings", base), { allowed: true });
});
(0, node_test_1.default)("reconciliation semantics: authoritative observations replace canonical value", () => {
    const reconciler = new reconciliation_1.Reconciler();
    strict_1.default.equal(reconciler.acceptRealtime({ value: 1 }, 100, 1000), true);
    strict_1.default.equal(reconciler.acceptAuthoritative({ value: 2 }, 200, 2000), true);
    const state = reconciler.snapshot(2000);
    strict_1.default.deepEqual(state.value, { value: 2 });
    strict_1.default.deepEqual(state.advisoryValue, { value: 1 });
    strict_1.default.equal(state.meta.lastSource, "authoritative");
});
(0, node_test_1.default)("reconciliation semantics: older authoritative observations cannot overwrite newer ones", () => {
    const reconciler = new reconciliation_1.Reconciler();
    strict_1.default.equal(reconciler.acceptAuthoritative({ value: 10 }, 500, 1000), true);
    strict_1.default.equal(reconciler.acceptAuthoritative({ value: 9 }, 400, 2000), false);
    strict_1.default.deepEqual(reconciler.snapshot(2000).value, { value: 10 });
    strict_1.default.equal(reconciler.snapshot(2000).meta.authoritativeVersion, 1);
});
(0, node_test_1.default)("reconciliation semantics: realtime observations remain advisory and never become canonical", () => {
    const reconciler = new reconciliation_1.Reconciler();
    strict_1.default.equal(reconciler.acceptAuthoritative({ value: 10 }, 500, 1000), true);
    strict_1.default.equal(reconciler.acceptRealtime({ value: 11 }, 600, 1100), true);
    const state = reconciler.snapshot(1100);
    strict_1.default.deepEqual(state.value, { value: 10 });
    strict_1.default.deepEqual(state.advisoryValue, { value: 11 });
    strict_1.default.equal(state.meta.authoritativeVersion, 1);
    strict_1.default.equal(state.meta.realtimeVersion, 1);
});
(0, node_test_1.default)("reconciliation semantics: realtime observations do not refresh canonical freshness", () => {
    const reconciler = new reconciliation_1.Reconciler();
    strict_1.default.equal(reconciler.acceptAuthoritative({ value: 1 }, 100, 1000), true);
    strict_1.default.equal(reconciler.acceptRealtime({ value: 2 }, 200, 15000), true);
    const state = reconciler.snapshot(15000);
    strict_1.default.equal(state.meta.lastAuthoritativeAtMs, 1000);
    strict_1.default.notEqual(state.freshness, "fresh");
    strict_1.default.equal(state.freshness, "degraded");
    strict_1.default.equal(reconciler.snapshot(22001).freshness, "stale");
});
(0, node_test_1.default)("reconciliation semantics: version counters remain monotonic", () => {
    const reconciler = new reconciliation_1.Reconciler();
    strict_1.default.equal(reconciler.snapshot(0).meta.authoritativeVersion, 0);
    strict_1.default.equal(reconciler.acceptAuthoritative({ value: 1 }, 100, 1000), true);
    strict_1.default.equal(reconciler.snapshot(1000).meta.authoritativeVersion, 1);
    strict_1.default.equal(reconciler.acceptAuthoritative({ value: 2 }, 200, 2000), true);
    strict_1.default.equal(reconciler.snapshot(2000).meta.authoritativeVersion, 2);
    strict_1.default.equal(reconciler.acceptRealtime({ value: 3 }, 300, 3000), true);
    strict_1.default.equal(reconciler.snapshot(3000).meta.realtimeVersion, 1);
    strict_1.default.equal(reconciler.acceptRealtime({ value: 4 }, 400, 4000), true);
    strict_1.default.equal(reconciler.snapshot(4000).meta.realtimeVersion, 2);
    const rejected = reconciler.acceptRealtime({ value: 5 }, 250, 5000);
    strict_1.default.equal(rejected, false);
    strict_1.default.equal(reconciler.snapshot(5000).meta.realtimeVersion, 2);
});
(0, node_test_1.default)("lifecycle identifiers survive normalization without being renamed or dropped", () => {
    const raw = {
        decision_id: "dec-1",
        correlation_id: "corr-1",
        execution_id: "exec-1",
        receipt_id: "rcpt-1",
        outcome_id: "out-1",
        sizing_id: "size-1",
        opportunity_id: "opp-1",
        route_id: "route-1",
        action: "execute",
        tx_hash: "0xabc",
    };
    const normalized = (0, canonical_1.normalizeTransaction)(raw);
    strict_1.default.equal(normalized.decisionId, "dec-1");
    strict_1.default.equal(normalized.correlationId, "corr-1");
    strict_1.default.equal(normalized.executionId, "exec-1");
    strict_1.default.equal(normalized.receiptId, "rcpt-1");
    strict_1.default.equal(normalized.outcomeId, "out-1");
    strict_1.default.equal(normalized.sizingId, "size-1");
    strict_1.default.equal(normalized.opportunityId, "opp-1");
    strict_1.default.equal(normalized.routeId, "route-1");
    strict_1.default.equal(normalized.action, "execute");
});
(0, node_test_1.default)("lifecycle identifiers accept the camelCase representation without replacement", () => {
    const normalized = (0, canonical_1.normalizeTransaction)({
        decisionId: "dec-2",
        correlationId: "corr-2",
        executionId: "exec-2",
        receiptId: "rcpt-2",
        outcomeId: "out-2",
        sizingId: "size-2",
        opportunityId: "opp-2",
        routeId: "route-2",
    });
    strict_1.default.equal(normalized.decisionId, "dec-2");
    strict_1.default.equal(normalized.correlationId, "corr-2");
    strict_1.default.equal(normalized.executionId, "exec-2");
    strict_1.default.equal(normalized.receiptId, "rcpt-2");
    strict_1.default.equal(normalized.outcomeId, "out-2");
    strict_1.default.equal(normalized.sizingId, "size-2");
    strict_1.default.equal(normalized.opportunityId, "opp-2");
    strict_1.default.equal(normalized.routeId, "route-2");
});
(0, node_test_1.default)("lifecycle identifiers are never fabricated when absent", () => {
    const normalized = (0, canonical_1.normalizeTransaction)({ decision_id: "dec-only" });
    strict_1.default.equal(normalized.decisionId, "dec-only");
    strict_1.default.equal(normalized.correlationId, undefined);
    strict_1.default.equal(normalized.executionId, undefined);
    strict_1.default.equal(normalized.receiptId, undefined);
    strict_1.default.equal(normalized.outcomeId, undefined);
    strict_1.default.equal(normalized.sizingId, undefined);
    strict_1.default.equal(normalized.routeId, undefined);
});
(0, node_test_1.default)("decision adapter preserves correlation and route identity across the contract boundary", async () => {
    const response = {
        ...canonical(canonicalContracts_1.CANONICAL_READ_CONTRACTS.xaiDecision.truthFamily, canonicalContracts_1.CANONICAL_READ_CONTRACTS.xaiDecision.readModel),
        item: {
            decision_id: "dec-9",
            correlation_id: "corr-9",
            execution_id: "exec-9",
            receipt_id: "rcpt-9",
            outcome_id: "out-9",
            sizing_id: "size-9",
            opportunity_id: "opp-9",
            route_id: "route-9",
            action: "hold",
        },
    };
    const { restore } = installFetch(response);
    try {
        const out = await (0, canonical_1.getXaiDecision)("https://api.example.test", "dec-9");
        strict_1.default.equal(out.decisionId, "dec-9");
        strict_1.default.equal(out.correlationId, "corr-9");
        strict_1.default.equal(out.executionId, "exec-9");
        strict_1.default.equal(out.receiptId, "rcpt-9");
        strict_1.default.equal(out.outcomeId, "out-9");
        strict_1.default.equal(out.sizingId, "size-9");
        strict_1.default.equal(out.opportunityId, "opp-9");
        strict_1.default.equal(out.routeId, "route-9");
        strict_1.default.equal(out.action, "hold");
        strict_1.default.equal(out.lifecycle?.decision.decisionId, "dec-9");
    }
    finally {
        restore();
    }
});
