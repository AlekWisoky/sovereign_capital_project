import test from "node:test";
import { strict as assert } from "node:assert";

import { capitalTruthHealthLegacyFields, normalizeCapitalTruthHealth } from "../src/commandCenter/capitalTruthHealth";
import type { FundHealthSummary, LaunchSummary } from "../src/commandCenter/types";
import { fundHealthHoldLine, fundHealthHoldReasonCodes } from "../src/utils/fund";
import { launchWhyNotLines } from "../src/utils/launch";

test("normalizeCapitalTruthHealth reads contract payloads and emits legacy fields", () => {
  const health = normalizeCapitalTruthHealth({
    status: "degraded",
    blocked: true,
    reason_codes: ["capital_truth_degraded"],
    freshness_class: "stale",
    freshness_reason_codes: ["capital_truth_freshness_stale"],
    next_action: "refresh_capital_truth_snapshot",
    reliability_class: "fragile",
    reliability_reason_codes: ["capital_truth_reliability_fragile"],
    state_contract: { status: "blocked", blocked: true, reason_code: "capital_truth_degraded" },
  });
  assert.equal(health?.status, "degraded");
  assert.deepEqual(health?.reasonCodes, ["capital_truth_degraded"]);
  assert.equal(health?.freshnessClass, "stale");
  assert.equal(health?.stateContract?.status, "blocked");
  assert.equal(capitalTruthHealthLegacyFields(health).capitalTruthFreshnessClass, "stale");
});

test("fund helpers fall back to capitalTruthHealth when flattened hold fields are absent", () => {
  const summary: FundHealthSummary = {
    fundStage: "private_fund",
    riskPosture: "defensive",
    riskScore: 0.62,
    capitalTruthHealth: {
      status: "degraded",
      blocked: true,
      reasonCodes: ["capital_truth_degraded"],
      nextAction: "refresh_capital_truth_snapshot",
    },
  };
  assert.deepEqual(fundHealthHoldReasonCodes(summary), ["capital_truth_degraded"]);
  assert.equal(fundHealthHoldLine(summary), "capital truth degraded · next refresh capital truth snapshot");
});

test("launch why-not lines fall back to blocked family capitalTruthHealth", () => {
  const summary: LaunchSummary = {
    currentLaunchMode: "STAGED_MULTI_STRATEGY",
    activeFamilies: ["flash_arb"],
    nextRecommendedFamily: "",
    blockedFamilies: { funding_arb: "capital_truth_degraded" },
    blockedFamilyDetails: {
      funding_arb: {
        reasonCode: "capital_not_ready",
        blockedBy: [],
        capitalTruthHealth: {
          blocked: true,
          reasonCodes: ["capital_truth_degraded"],
          nextAction: "refresh_capital_truth_snapshot",
        },
      },
    },
    families: [],
    reasons: [],
  };
  assert.deepEqual(launchWhyNotLines(summary), ["funding arb = capital truth degraded · next refresh capital truth snapshot"]);
});
