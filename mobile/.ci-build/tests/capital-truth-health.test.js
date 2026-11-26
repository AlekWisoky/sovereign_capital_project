"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const node_assert_1 = require("node:assert");
const capitalTruthHealth_1 = require("../src/commandCenter/capitalTruthHealth");
const fund_1 = require("../src/utils/fund");
const launch_1 = require("../src/utils/launch");
(0, node_test_1.default)("normalizeCapitalTruthHealth reads contract payloads and emits legacy fields", () => {
    const health = (0, capitalTruthHealth_1.normalizeCapitalTruthHealth)({
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
    node_assert_1.strict.equal(health?.status, "degraded");
    node_assert_1.strict.deepEqual(health?.reasonCodes, ["capital_truth_degraded"]);
    node_assert_1.strict.equal(health?.freshnessClass, "stale");
    node_assert_1.strict.equal(health?.stateContract?.status, "blocked");
    node_assert_1.strict.equal((0, capitalTruthHealth_1.capitalTruthHealthLegacyFields)(health).capitalTruthFreshnessClass, "stale");
});
(0, node_test_1.default)("fund helpers fall back to capitalTruthHealth when flattened hold fields are absent", () => {
    const summary = {
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
    node_assert_1.strict.deepEqual((0, fund_1.fundHealthHoldReasonCodes)(summary), ["capital_truth_degraded"]);
    node_assert_1.strict.equal((0, fund_1.fundHealthHoldLine)(summary), "capital truth degraded · next refresh capital truth snapshot");
});
(0, node_test_1.default)("launch why-not lines fall back to blocked family capitalTruthHealth", () => {
    const summary = {
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
    node_assert_1.strict.deepEqual((0, launch_1.launchWhyNotLines)(summary), ["funding arb = capital truth degraded · next refresh capital truth snapshot"]);
});
