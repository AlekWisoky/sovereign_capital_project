import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import {
  CANONICAL_READ_CONTRACTS,
  MUTATION_CONTRACTS,
  canonicalCommandCenterAuditTail,
  canonicalCommandCenterControl,
  canonicalCommandCenterExplain,
  canonicalCommandCenterSnapshot,
  canonicalCapitalExplain,
  canonicalEngineState,
  canonicalExecutionQuality,
  canonicalFundSummary,
  canonicalKdsState,
  canonicalLaunchFamilyDetail,
  canonicalLaunchState,
  canonicalReliabilityState,
  canonicalRiskLiveState,
  canonicalServiceHealth,
  canonicalSpreadOpportunities,
  canonicalWealthGoal,
  canonicalXaiDecision,
  canonicalXaiLatest,
} from "../src/api/canonicalContracts";
import { getXaiDecision, normalizeTransaction } from "../src/api/canonical";
import { Reconciler } from "../src/api/reconciliation";
import { guardMutation, type MutationGuardContext } from "../src/api/mutationGuard";

type FetchCall = { url: string; init?: RequestInit };

function installFetch(response: unknown): { calls: FetchCall[]; restore: () => void } {
  const calls: FetchCall[] = [];
  const previous = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    return {
      ok: true,
      status: 200,
      json: async () => response,
    } as Response;
  }) as typeof fetch;
  return { calls, restore: () => { globalThis.fetch = previous; } };
}

const canonical = (truthFamily: string, readModel: string) => ({
  ok: true,
  summaryContract: {
    contractVersion: "canonical_summary_read_contract_v1",
    truthFamily,
    readModel,
  },
});

test("canonical read adapters preserve the existing summary contract and exact endpoint", async () => {
  const response = canonical(
    CANONICAL_READ_CONTRACTS.commandCenterAuditTail.truthFamily,
    CANONICAL_READ_CONTRACTS.commandCenterAuditTail.readModel,
  );
  const { calls, restore } = installFetch(response);
  try {
    await canonicalCommandCenterAuditTail("https://api.example.test", 7, "secret");
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "https://api.example.test/api/commandcenter/audit/tail?limit=7");
    assert.equal(calls[0].init?.method, undefined);
    assert.deepEqual((calls[0].init?.headers ?? {}), { "X-Admin-Key": "secret" });
  } finally {
    restore();
  }
});

test("parameterized canonical adapters encode path parameters and validate read-model identity", async () => {
  const response = canonical(
    CANONICAL_READ_CONTRACTS.launchFamilyDetail.truthFamily,
    CANONICAL_READ_CONTRACTS.launchFamilyDetail.readModel,
  );
  const { calls, restore } = installFetch(response);
  try {
    await canonicalLaunchFamilyDetail("https://api.example.test", "family/a", "secret");
    assert.equal(calls[0].url, "https://api.example.test/api/launch/family/family%2Fa");
  } finally {
    restore();
  }
});

test("canonical spread-opportunity adapter enforces the declared projection identity", async () => {
  const response = {
    ...canonical(
      CANONICAL_READ_CONTRACTS.spreadOpportunities.truthFamily,
      CANONICAL_READ_CONTRACTS.spreadOpportunities.readModel,
    ),
    items: [],
  };
  const { calls, restore } = installFetch(response);
  try {
    const out = await canonicalSpreadOpportunities("https://api.example.test", "secret");
    assert.deepEqual(out.items, []);
    assert.equal(calls[0].url, "https://api.example.test/api/spread/opportunities");
    assert.equal(calls[0].init?.method, undefined);
  } finally {
    restore();
  }
});

test("canonical adapter rejects a mismatched backend truth family", async () => {
  const response = canonical("wrong_family", CANONICAL_READ_CONTRACTS.xaiDecision.readModel);
  const { restore } = installFetch(response);
  await assert.rejects(
    () => canonicalXaiDecision("https://api.example.test", "decision/1"),
    /canonical_truth_family_mismatch/,
  );
  restore();
});

test("mutation contracts encode backend capability and preserve admin-key authorization", async () => {
  assert.equal(MUTATION_CONTRACTS.commandCenterControl.method, "POST");
  assert.equal(MUTATION_CONTRACTS.commandCenterControl.path, "/api/commandcenter/control");
  assert.equal(MUTATION_CONTRACTS.commandCenterControl.capability, "admin:write");
  assert.equal(MUTATION_CONTRACTS.launchMode.capability, "admin:write");
  assert.equal(MUTATION_CONTRACTS.tradeOpportunity.capability, "execute");
  assert.equal(MUTATION_CONTRACTS.tradeOpportunity.authority, "execution");
  assert.equal(MUTATION_CONTRACTS.tradeOpportunity.requiresLiveAuthority, true);
  assert.equal(MUTATION_CONTRACTS.withdrawExecute.capability, "admin:write");
  assert.equal(MUTATION_CONTRACTS.withdrawExecute.authority, "capital_write");
  assert.equal(MUTATION_CONTRACTS.withdrawExecute.requiresLiveAuthority, true);

  const response = { ok: true };
  const { calls, restore } = installFetch(response);
  try {
    await canonicalCommandCenterControl(
      "https://api.example.test",
      { auto_trading: false },
      "operator-confirmed",
      "secret",
    );
    assert.equal(calls[0].url, "https://api.example.test/api/commandcenter/control");
    assert.equal(calls[0].init?.method, "POST");
    assert.equal(calls[0].init?.headers && (calls[0].init?.headers as Record<string, string>)["X-Admin-Key"], "secret");
    assert.deepEqual(JSON.parse(String(calls[0].init?.body)), {
      patch: { auto_trading: false },
      reason: "operator-confirmed",
    });
  } finally {
    restore();
  }
});

test("canonical engine adapter uses GET and its declared engine projection identity", async () => {
  const response = {
    ...canonical(
      CANONICAL_READ_CONTRACTS.enginesState.truthFamily,
      CANONICAL_READ_CONTRACTS.enginesState.readModel,
    ),
    summary: { engines: [] },
  };
  const { calls, restore } = installFetch(response);
  try {
    const out = await canonicalEngineState("https://api.example.test");
    assert.equal(out.summaryContract?.truthFamily, "engine_state");
    assert.equal(calls[0].url, "https://api.example.test/api/engines/state");
    assert.equal(calls[0].init?.method, undefined);
  } finally {
    restore();
  }
});


test("command-center provider routes canonical reads through the typed contract layer", () => {
  const source = readFileSync("src/commandCenter/provider.ts", "utf8");
  assert.match(source, /canonicalCommandCenterSnapshot/);
  assert.match(source, /canonicalEngineState/);
  assert.match(source, /canonicalFundSummary/);
  assert.match(source, /canonicalExecutionQuality/);
  assert.match(source, /canonicalRiskLiveState/);
  assert.match(source, /canonicalServiceHealth/);
  assert.match(source, /canonicalCommandCenterControl/);
  assert.doesNotMatch(source, /apiGet\(baseUrl,\s*["']\/api\/(commandcenter\/snapshot|engines\/state|fund\/summary|system\/execution\/quality|risk\/live-state|system\/services)/);
});


test("decision adapter preserves one canonical lifecycle lineage", async () => {
  const response = {
    ...canonical(CANONICAL_READ_CONTRACTS.xaiDecision.truthFamily, CANONICAL_READ_CONTRACTS.xaiDecision.readModel),
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
    const out = await getXaiDecision("https://api.example.test", "dec-1");
    assert.equal(out.lifecycle?.decision.decisionId, "dec-1");
    assert.equal(out.lifecycle?.sizing.sizingId, "size-1");
    assert.equal(out.lifecycle?.execution.executionId, "exec-1");
    assert.equal(out.lifecycle?.receipt.receiptId, "rcpt-1");
    assert.equal(out.lifecycle?.settlement.outcomeId, "out-1");
    assert.equal(out.lifecycle?.settlement.verified, true);
    assert.equal(out.lifecycle?.learning.recorded, true);
  } finally {
    restore();
  }
});

// ---------------------------------------------------------------------------
// Prompt 01A contract-freeze gate.
// These tests freeze the *existing* canonical contracts. They assert only what
// the current implementation already declares; they do not invent endpoints,
// truth families, read models, authorities, or lifecycle identifiers.
// ---------------------------------------------------------------------------

test("canonical endpoint identity: every read contract is GET on a unique /api path", () => {
  const entries = Object.entries(CANONICAL_READ_CONTRACTS);
  assert.ok(entries.length > 0);
  const seenPaths = new Set<string>();
  const seenKeys = new Set<string>();
  for (const [key, contract] of entries) {
    assert.equal(seenKeys.has(key), false, `duplicate canonical contract key: ${key}`);
    seenKeys.add(key);
    assert.equal(contract.method, "GET", `read contract ${key} must be GET`);
    assert.match(contract.path, /^\/api\//, `read contract ${key} must target /api`);
    assert.equal(seenPaths.has(contract.path), false, `duplicate canonical endpoint: ${contract.path}`);
    seenPaths.add(contract.path);
    assert.equal(typeof contract.truthFamily, "string");
    assert.equal(typeof contract.readModel, "string");
  }
});

test("canonical endpoint identity: adapters hit the declared endpoint exactly, with no fallback", async () => {
  type Contract = (typeof CANONICAL_READ_CONTRACTS)[keyof typeof CANONICAL_READ_CONTRACTS];
  const cases: Array<{ contract: Contract; call: (base: string) => Promise<unknown> }> = [
    { contract: CANONICAL_READ_CONTRACTS.commandCenterSnapshot, call: (b) => canonicalCommandCenterSnapshot(b) },
    { contract: CANONICAL_READ_CONTRACTS.commandCenterExplain, call: (b) => canonicalCommandCenterExplain(b) },
    { contract: CANONICAL_READ_CONTRACTS.enginesState, call: (b) => canonicalEngineState(b) },
    { contract: CANONICAL_READ_CONTRACTS.fundSummary, call: (b) => canonicalFundSummary(b) },
    { contract: CANONICAL_READ_CONTRACTS.spreadOpportunities, call: (b) => canonicalSpreadOpportunities(b) },
    { contract: CANONICAL_READ_CONTRACTS.launchState, call: (b) => canonicalLaunchState(b) },
    { contract: CANONICAL_READ_CONTRACTS.reliabilityState, call: (b) => canonicalReliabilityState(b) },
    { contract: CANONICAL_READ_CONTRACTS.kdsState, call: (b) => canonicalKdsState(b) },
    { contract: CANONICAL_READ_CONTRACTS.riskLiveState, call: (b) => canonicalRiskLiveState(b) },
    { contract: CANONICAL_READ_CONTRACTS.executionQuality, call: (b) => canonicalExecutionQuality(b) },
    { contract: CANONICAL_READ_CONTRACTS.serviceHealth, call: (b) => canonicalServiceHealth(b) },
    { contract: CANONICAL_READ_CONTRACTS.capitalExplain, call: (b) => canonicalCapitalExplain(b) },
    { contract: CANONICAL_READ_CONTRACTS.wealthGoal, call: (b) => canonicalWealthGoal(b) },
  ];
  for (const { contract, call } of cases) {
    const { calls, restore } = installFetch(canonical(contract.truthFamily, contract.readModel));
    try {
      await call("https://api.example.test");
      assert.equal(calls.length, 1, `${contract.path} issued ${calls.length} calls`);
      assert.equal(calls[0].url, `https://api.example.test${contract.path}`);
      assert.equal(calls[0].init?.method, undefined);
    } finally {
      restore();
    }
  }
});

test("truth-family identity: a matching truth family is accepted", async () => {
  const response = {
    ...canonical(
      CANONICAL_READ_CONTRACTS.xaiLatest.truthFamily,
      CANONICAL_READ_CONTRACTS.xaiLatest.readModel,
    ),
    items: [],
  };
  const { restore } = installFetch(response);
  try {
    const out = await canonicalXaiLatest("https://api.example.test");
    assert.equal(out.summaryContract?.truthFamily, CANONICAL_READ_CONTRACTS.xaiLatest.truthFamily);
  } finally {
    restore();
  }
});

test("truth-family identity: a mismatched truth family fails closed", async () => {
  const response = canonical("not_spread_opportunities", CANONICAL_READ_CONTRACTS.spreadOpportunities.readModel);
  const { restore } = installFetch(response);
  try {
    await assert.rejects(
      () => canonicalSpreadOpportunities("https://api.example.test"),
      /canonical_truth_family_mismatch/,
    );
  } finally {
    restore();
  }
});

test("read-model identity: a mismatched read model fails closed", async () => {
  const response = canonical(CANONICAL_READ_CONTRACTS.enginesState.truthFamily, "not_the_engine_projection");
  const { restore } = installFetch(response);
  try {
    await assert.rejects(
      () => canonicalEngineState("https://api.example.test"),
      /canonical_read_model_mismatch/,
    );
  } finally {
    restore();
  }
});

test("read-model identity: a missing summary contract fails closed", async () => {
  const { restore } = installFetch({ ok: true });
  try {
    await assert.rejects(
      () => canonicalServiceHealth("https://api.example.test"),
      /canonical_contract_missing/,
    );
  } finally {
    restore();
  }
});

test("mutation authority: existing mutation contracts preserve their authority boundaries", () => {
  const control = MUTATION_CONTRACTS.commandCenterControl;
  assert.equal(control.authority, "control");
  assert.equal(control.capability, "admin:write");
  assert.equal(control.requiresLiveAuthority, false);

  const execution = MUTATION_CONTRACTS.tradeOpportunity;
  assert.equal(execution.authority, "execution");
  assert.equal(execution.capability, "execute");
  assert.equal(execution.requiresLiveAuthority, true);

  const capitalWrite = MUTATION_CONTRACTS.withdrawExecute;
  assert.equal(capitalWrite.authority, "capital_write");
  assert.equal(capitalWrite.capability, "admin:write");
  assert.equal(capitalWrite.requiresLiveAuthority, true);

  const chainControl = MUTATION_CONTRACTS.selectChain;
  assert.equal(chainControl.authority, "chain_control");
  assert.equal(chainControl.capability, "admin:write");
  assert.equal(chainControl.requiresLiveAuthority, false);

  const allowedAuthorities = new Set(["control", "execution", "capital_write", "chain_control"]);
  const seenPaths = new Set<string>();
  for (const [key, contract] of Object.entries(MUTATION_CONTRACTS)) {
    assert.equal(contract.method, "POST", `${key} must be POST`);
    assert.equal(allowedAuthorities.has(contract.authority), true, `${key} has unknown authority`);
    assert.equal(seenPaths.has(contract.path), false, `duplicate mutation endpoint: ${contract.path}`);
    seenPaths.add(contract.path);
  }
});

test("mutation authority: guarded mutations stay fail-closed without satisfying authority", () => {
  const base: MutationGuardContext = {
    role: "operator",
    locked: false,
    adminKeyPresent: true,
    backendReachable: true,
    backendLiveAuthority: false,
    explicitConfirmation: true,
  };

  assert.deepEqual(guardMutation("execution", base), { allowed: false, reasonCode: "live_authority_disabled" });
  assert.deepEqual(guardMutation("withdrawal", base), { allowed: false, reasonCode: "live_authority_disabled" });
  assert.deepEqual(guardMutation("settings", { ...base, adminKeyPresent: false }), { allowed: false, reasonCode: "admin_key_required" });
  assert.deepEqual(guardMutation("chain_control", { ...base, explicitConfirmation: false }), { allowed: false, reasonCode: "explicit_confirmation_required" });
  assert.deepEqual(guardMutation("settings", { ...base, backendReachable: false }), { allowed: false, reasonCode: "backend_unavailable" });
  assert.deepEqual(guardMutation("settings", { ...base, role: "read_only" }), { allowed: false, reasonCode: "operator_required" });
  assert.deepEqual(guardMutation("settings", { ...base, locked: true }), { allowed: false, reasonCode: "operator_locked" });
  assert.deepEqual(guardMutation("settings", base), { allowed: true });
});

test("reconciliation semantics: authoritative observations replace canonical value", () => {
  const reconciler = new Reconciler<{ value: number }>();
  assert.equal(reconciler.acceptRealtime({ value: 1 }, 100, 1_000), true);
  assert.equal(reconciler.acceptAuthoritative({ value: 2 }, 200, 2_000), true);
  const state = reconciler.snapshot(2_000);
  assert.deepEqual(state.value, { value: 2 });
  assert.deepEqual(state.advisoryValue, { value: 1 });
  assert.equal(state.meta.lastSource, "authoritative");
});

test("reconciliation semantics: older authoritative observations cannot overwrite newer ones", () => {
  const reconciler = new Reconciler<{ value: number }>();
  assert.equal(reconciler.acceptAuthoritative({ value: 10 }, 500, 1_000), true);
  assert.equal(reconciler.acceptAuthoritative({ value: 9 }, 400, 2_000), false);
  assert.deepEqual(reconciler.snapshot(2_000).value, { value: 10 });
  assert.equal(reconciler.snapshot(2_000).meta.authoritativeVersion, 1);
});

test("reconciliation semantics: realtime observations remain advisory and never become canonical", () => {
  const reconciler = new Reconciler<{ value: number }>();
  assert.equal(reconciler.acceptAuthoritative({ value: 10 }, 500, 1_000), true);
  assert.equal(reconciler.acceptRealtime({ value: 11 }, 600, 1_100), true);
  const state = reconciler.snapshot(1_100);
  assert.deepEqual(state.value, { value: 10 });
  assert.deepEqual(state.advisoryValue, { value: 11 });
  assert.equal(state.meta.authoritativeVersion, 1);
  assert.equal(state.meta.realtimeVersion, 1);
});

test("reconciliation semantics: realtime observations do not refresh canonical freshness", () => {
  const reconciler = new Reconciler<{ value: number }>();
  assert.equal(reconciler.acceptAuthoritative({ value: 1 }, 100, 1_000), true);
  assert.equal(reconciler.acceptRealtime({ value: 2 }, 200, 15_000), true);
  const state = reconciler.snapshot(15_000);
  assert.equal(state.meta.lastAuthoritativeAtMs, 1_000);
  assert.notEqual(state.freshness, "fresh");
  assert.equal(state.freshness, "degraded");
  assert.equal(reconciler.snapshot(22_001).freshness, "stale");
});

test("reconciliation semantics: version counters remain monotonic", () => {
  const reconciler = new Reconciler<{ value: number }>();
  assert.equal(reconciler.snapshot(0).meta.authoritativeVersion, 0);
  assert.equal(reconciler.acceptAuthoritative({ value: 1 }, 100, 1_000), true);
  assert.equal(reconciler.snapshot(1_000).meta.authoritativeVersion, 1);
  assert.equal(reconciler.acceptAuthoritative({ value: 2 }, 200, 2_000), true);
  assert.equal(reconciler.snapshot(2_000).meta.authoritativeVersion, 2);

  assert.equal(reconciler.acceptRealtime({ value: 3 }, 300, 3_000), true);
  assert.equal(reconciler.snapshot(3_000).meta.realtimeVersion, 1);
  assert.equal(reconciler.acceptRealtime({ value: 4 }, 400, 4_000), true);
  assert.equal(reconciler.snapshot(4_000).meta.realtimeVersion, 2);

  const rejected = reconciler.acceptRealtime({ value: 5 }, 250, 5_000);
  assert.equal(rejected, false);
  assert.equal(reconciler.snapshot(5_000).meta.realtimeVersion, 2);
});

test("lifecycle identifiers survive normalization without being renamed or dropped", () => {
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
  const normalized = normalizeTransaction(raw);
  assert.equal(normalized.decisionId, "dec-1");
  assert.equal(normalized.correlationId, "corr-1");
  assert.equal(normalized.executionId, "exec-1");
  assert.equal(normalized.receiptId, "rcpt-1");
  assert.equal(normalized.outcomeId, "out-1");
  assert.equal(normalized.sizingId, "size-1");
  assert.equal(normalized.opportunityId, "opp-1");
  assert.equal(normalized.routeId, "route-1");
  assert.equal(normalized.action, "execute");
});

test("lifecycle identifiers accept the camelCase representation without replacement", () => {
  const normalized = normalizeTransaction({
    decisionId: "dec-2",
    correlationId: "corr-2",
    executionId: "exec-2",
    receiptId: "rcpt-2",
    outcomeId: "out-2",
    sizingId: "size-2",
    opportunityId: "opp-2",
    routeId: "route-2",
  });
  assert.equal(normalized.decisionId, "dec-2");
  assert.equal(normalized.correlationId, "corr-2");
  assert.equal(normalized.executionId, "exec-2");
  assert.equal(normalized.receiptId, "rcpt-2");
  assert.equal(normalized.outcomeId, "out-2");
  assert.equal(normalized.sizingId, "size-2");
  assert.equal(normalized.opportunityId, "opp-2");
  assert.equal(normalized.routeId, "route-2");
});

test("lifecycle identifiers are never fabricated when absent", () => {
  const normalized = normalizeTransaction({ decision_id: "dec-only" });
  assert.equal(normalized.decisionId, "dec-only");
  assert.equal(normalized.correlationId, undefined);
  assert.equal(normalized.executionId, undefined);
  assert.equal(normalized.receiptId, undefined);
  assert.equal(normalized.outcomeId, undefined);
  assert.equal(normalized.sizingId, undefined);
  assert.equal(normalized.routeId, undefined);
});

test("decision adapter preserves correlation and route identity across the contract boundary", async () => {
  const response = {
    ...canonical(CANONICAL_READ_CONTRACTS.xaiDecision.truthFamily, CANONICAL_READ_CONTRACTS.xaiDecision.readModel),
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
    const out = await getXaiDecision("https://api.example.test", "dec-9");
    assert.equal(out.decisionId, "dec-9");
    assert.equal(out.correlationId, "corr-9");
    assert.equal(out.executionId, "exec-9");
    assert.equal(out.receiptId, "rcpt-9");
    assert.equal(out.outcomeId, "out-9");
    assert.equal(out.sizingId, "size-9");
    assert.equal(out.opportunityId, "opp-9");
    assert.equal(out.routeId, "route-9");
    assert.equal(out.action, "hold");
    assert.equal(out.lifecycle?.decision.decisionId, "dec-9");
  } finally {
    restore();
  }
});
