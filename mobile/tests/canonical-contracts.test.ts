import assert from "node:assert/strict";
import test from "node:test";

import {
  CANONICAL_READ_CONTRACTS,
  MUTATION_CONTRACTS,
  canonicalCommandCenterAuditTail,
  canonicalCommandCenterControl,
  canonicalEngineState,
  canonicalLaunchFamilyDetail,
  canonicalXaiDecision,
} from "../src/api/canonicalContracts";

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
