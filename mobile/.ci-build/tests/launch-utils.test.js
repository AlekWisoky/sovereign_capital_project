"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const node_assert_1 = require("node:assert");
const launch_1 = require("../src/utils/launch");
const family = {
    family: 'funding_arb',
    score: 0.82,
    ready: true,
    status: 'eligible',
    reasons: [],
    blockers: [],
    count: 8,
    successRate: 0.84,
    gasEfficiency: 1.2,
    calibrationQuality: 0.98,
    stageAllowed: true,
    active: false,
    rolloutIndex: 1,
    telemetrySufficient: true,
    capitalReady: true,
    internalPrimeReady: true,
};
(0, node_test_1.default)('launch status label prefers ready state', () => {
    node_assert_1.strict.equal((0, launch_1.launchStatusLabel)(family), 'Ready');
    node_assert_1.strict.equal((0, launch_1.familyDependencyRows)(family).every((x) => x.ok), true);
});
(0, node_test_1.default)('launch recommendation helpers prefer explicit recommendation', () => {
    const summary = {
        currentLaunchMode: 'STAGED_MULTI_STRATEGY',
        activeFamilies: ['flash_arb'],
        nextRecommendedFamily: 'funding_arb',
        blockedFamilies: { mev_search: 'private_routing_not_ready' },
        families: [family],
        reasons: ['stable_readiness'],
        recommendation: {
            nextFamily: 'funding_arb',
            whyNow: ['stable_readiness', 'capital_ready'],
            whyNotOthers: { mev_search: 'private_routing_not_ready' },
            whyNotOthersDetails: {
                mev_search: {
                    reasonCode: 'internal_prime_not_ready',
                    blockedBy: ['internal_prime_journal_borrowed_mismatch'],
                    suggestedNextAction: 'repair_internal_prime_accounting',
                    internalPrimeReasonCodes: ['internal_prime_journal_borrowed_mismatch'],
                },
            },
            rollbackRecommendation: 'revert_to_v1_learning',
        },
        rollbackRecommendation: 'revert_to_v1_learning',
    };
    node_assert_1.strict.equal(JSON.stringify((0, launch_1.launchWhyNow)(summary)), JSON.stringify(['stable_readiness', 'capital_ready']));
    node_assert_1.strict.equal((0, launch_1.launchRollbackText)(summary), 'revert_to_v1_learning');
    node_assert_1.strict.equal(JSON.stringify((0, launch_1.launchWhyNotLines)(summary)), JSON.stringify([
        'mev search = internal prime journal borrowed mismatch · next repair internal prime accounting',
    ]));
    node_assert_1.strict.equal(JSON.stringify((0, launch_1.launchWhyNotPreview)(summary, 1)), JSON.stringify([
        'mev search = internal prime journal borrowed mismatch · next repair internal prime accounting',
    ]));
    node_assert_1.strict.equal((0, launch_1.launchWhyNotOverflowCount)(summary, 1), 0);
});
(0, node_test_1.default)('launch why-not preview truncates and reports overflow deterministically', () => {
    const summary = {
        currentLaunchMode: 'STAGED_MULTI_STRATEGY',
        activeFamilies: ['flash_arb'],
        nextRecommendedFamily: 'funding_arb',
        blockedFamilies: {
            mev_search: 'private_routing_not_ready',
            liquidations: 'capital_not_ready',
            stat_arb: 'observe_only',
        },
        blockedFamilyDetails: {
            mev_search: {
                reasonCode: 'internal_prime_not_ready',
                blockedBy: ['internal_prime_journal_borrowed_mismatch'],
                suggestedNextAction: 'repair_internal_prime_accounting',
                internalPrimeReasonCodes: ['internal_prime_journal_borrowed_mismatch'],
            },
            liquidations: {
                reasonCode: 'capital_not_ready',
                blockedBy: ['capital_truth_degraded'],
                suggestedNextAction: 'restore_capital_truth',
                capitalTruthReasonCodes: ['capital_truth_degraded'],
            },
            stat_arb: {
                reasonCode: 'observe_only',
                blockedBy: ['observe_only'],
            },
        },
        families: [family],
        reasons: ['stable_readiness'],
    };
    node_assert_1.strict.equal(JSON.stringify((0, launch_1.launchWhyNotPreview)(summary, 2)), JSON.stringify([
        'mev search = internal prime journal borrowed mismatch · next repair internal prime accounting',
        'liquidations = capital truth degraded · next restore capital truth',
    ]));
    node_assert_1.strict.equal((0, launch_1.launchWhyNotOverflowCount)(summary, 2), 1);
});
(0, node_test_1.default)('launch why-now falls back to hold reason codes when rollout is blocked', () => {
    const summary = {
        currentLaunchMode: 'STAGED_MULTI_STRATEGY',
        activeFamilies: ['flash_arb'],
        nextRecommendedFamily: '',
        blockedFamilies: { funding_arb: 'drawdown_hard_stop' },
        families: [family],
        reasons: [],
        holdReasonCode: 'drawdown_hard_stop',
        holdReasonCodes: ['drawdown_hard_stop'],
        recommendation: {
            nextFamily: '',
            whyNow: [],
            whyNotOthers: { funding_arb: 'drawdown_hard_stop' },
            holdReasonCode: 'drawdown_hard_stop',
            holdReasonCodes: ['drawdown_hard_stop'],
            suggestedNextAction: 'reduce_drawdown_and_clear_hard_stop',
        },
    };
    node_assert_1.strict.equal(JSON.stringify((0, launch_1.launchWhyNow)(summary)), JSON.stringify(['drawdown_hard_stop']));
});
(0, node_test_1.default)('launch recovery line prefers explicit recovery canon and falls back to top-level launch recovery', () => {
    const blockedSummary = {
        currentLaunchMode: 'STAGED_MULTI_STRATEGY',
        activeFamilies: ['flash_arb'],
        nextRecommendedFamily: '',
        blockedFamilies: { funding_arb: 'capital_truth_unavailable' },
        families: [family],
        reasons: [],
        recommendation: {
            nextFamily: '',
            whyNow: [],
            whyNotOthers: { funding_arb: 'capital_truth_unavailable' },
            recoveryReady: false,
            recoveryStatus: 'capital_truth_restore_required',
            recoveryReasonCode: 'capital_truth_unavailable',
            recoveryReasonCodes: ['capital_truth_unavailable'],
            recoveryNextAction: 'restore_capital_truth',
        },
    };
    node_assert_1.strict.equal((0, launch_1.launchRecoveryLine)(blockedSummary), 'capital truth unavailable · next restore capital truth');
    const topLevelRecovery = {
        currentLaunchMode: 'STAGED_MULTI_STRATEGY',
        activeFamilies: ['flash_arb'],
        nextRecommendedFamily: '',
        blockedFamilies: { funding_arb: 'internal_prime_journal_borrowed_mismatch' },
        families: [family],
        reasons: [],
        recoveryReady: false,
        recoveryStatus: 'internal_prime_reconciliation_required',
        recoveryReasonCode: 'internal_prime_journal_borrowed_mismatch',
        recoveryReasonCodes: ['internal_prime_journal_borrowed_mismatch'],
        recoveryNextAction: 'repair_internal_prime_accounting',
    };
    node_assert_1.strict.equal((0, launch_1.launchRecoveryLine)(topLevelRecovery), 'internal prime journal borrowed mismatch · next repair internal prime accounting');
});
(0, node_test_1.default)('launch recovery freshness line prefers explicit freshness canon and falls back to top-level launch recovery freshness', () => {
    const blockedSummary = {
        currentLaunchMode: 'STAGED_MULTI_STRATEGY',
        activeFamilies: ['flash_arb'],
        nextRecommendedFamily: '',
        blockedFamilies: { funding_arb: 'capital_truth_unavailable' },
        families: [family],
        reasons: [],
        recommendation: {
            nextFamily: '',
            whyNow: [],
            whyNotOthers: { funding_arb: 'capital_truth_unavailable' },
            recoveryFreshnessClass: 'unavailable',
            recoveryFreshnessReasonCode: 'capital_truth_freshness_unavailable',
            recoveryFreshnessReasonCodes: ['capital_truth_freshness_unavailable'],
            recoveryFreshnessNextAction: 'refresh_capital_truth_snapshot',
        },
    };
    node_assert_1.strict.equal((0, launch_1.launchRecoveryFreshnessLine)(blockedSummary), 'capital truth freshness unavailable · class unavailable · next refresh capital truth snapshot');
    const topLevelRecovery = {
        currentLaunchMode: 'STAGED_MULTI_STRATEGY',
        activeFamilies: ['flash_arb'],
        nextRecommendedFamily: '',
        blockedFamilies: { funding_arb: 'internal_prime_journal_borrowed_mismatch' },
        families: [family],
        reasons: [],
        recoveryFreshnessClass: 'stale',
        recoveryFreshnessReasonCode: 'internal_prime_reconciliation_freshness_stale',
        recoveryFreshnessReasonCodes: ['internal_prime_reconciliation_freshness_stale'],
        recoveryFreshnessNextAction: 'refresh_internal_prime_reconciliation',
    };
    node_assert_1.strict.equal((0, launch_1.launchRecoveryFreshnessLine)(topLevelRecovery), 'internal prime reconciliation freshness stale · class stale · next refresh internal prime reconciliation');
});
(0, node_test_1.default)('launch recovery history line surfaces degraded capital truth state', () => {
    const summary = {
        currentLaunchMode: 'STAGED_MULTI_STRATEGY',
        activeFamilies: ['flash_arb'],
        nextRecommendedFamily: '',
        blockedFamilies: { funding_arb: 'capital_truth_unavailable' },
        families: [family],
        reasons: [],
        recommendation: {
            nextFamily: '',
            whyNow: [],
            whyNotOthers: { funding_arb: 'capital_truth_unavailable' },
            recoveryHistoryComponent: 'capital_truth',
            recoveryHistoryStatus: 'degraded',
            recoveryDegradedSinceTsMs: 1700000000000,
            recoveryDegradedDurationMs: 60000,
        },
    };
    node_assert_1.strict.match((0, launch_1.launchRecoveryHistoryLine)(summary), /degraded/);
    node_assert_1.strict.match((0, launch_1.launchRecoveryHistoryLine)(summary), /capital truth/);
});
(0, node_test_1.default)('launch recovery history line includes count, severity, and last healthy markers', () => {
    const summary = {
        currentLaunchMode: 'STAGED_MULTI_STRATEGY',
        activeFamilies: ['flash_arb'],
        nextRecommendedFamily: '',
        blockedFamilies: { funding_arb: 'capital_truth_unavailable' },
        families: [family],
        reasons: [],
        recommendation: {
            nextFamily: '',
            whyNow: [],
            whyNotOthers: { funding_arb: 'capital_truth_unavailable' },
            recoveryHistoryComponent: 'capital_truth',
            recoveryHistoryStatus: 'degraded',
            recoveryDegradedCount: 4,
            recoveryLastHealthyTsMs: 1700000000000,
            recoveryDegradationSeverityClass: 'persistent',
        },
    };
    const line = (0, launch_1.launchRecoveryHistoryLine)(summary);
    node_assert_1.strict.match(line, /count 4/);
    node_assert_1.strict.match(line, /severity persistent/);
    node_assert_1.strict.match(line, /last healthy/);
});
(0, node_test_1.default)('launch recovery reliability line surfaces fragile recovered state', () => {
    const summary = {
        currentLaunchMode: 'STAGED_MULTI_STRATEGY',
        activeFamilies: ['flash_arb'],
        nextRecommendedFamily: '',
        blockedFamilies: { funding_arb: 'capital_truth_unavailable' },
        families: [family],
        reasons: [],
        recommendation: {
            nextFamily: '',
            whyNow: [],
            whyNotOthers: { funding_arb: 'capital_truth_unavailable' },
            recoveryReliabilityClass: 'fragile',
            recoveryReliabilityReasonCode: 'recovery_reliability_fragile',
            recoveryReliabilityReasonCodes: ['recovery_reliability_fragile', 'recovery_recovered_fragile'],
            recoveryReliabilityNextAction: 'restore_capital_truth',
            recoveryRecoveredFragile: true,
        },
    };
    const line = (0, launch_1.launchRecoveryReliabilityLine)(summary);
    node_assert_1.strict.match(line, /recovery reliability fragile/);
    node_assert_1.strict.match(line, /recovered fragile yes/);
    node_assert_1.strict.match(line, /restore capital truth/);
});
