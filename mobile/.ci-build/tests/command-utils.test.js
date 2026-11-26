"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const node_assert_1 = require("node:assert");
const command_1 = require("../src/utils/command");
(0, node_test_1.default)('command center hold helpers prefer explicit top-level hold canon', () => {
    const snapshot = {
        ok: true,
        portfolio: { navUsd: 1000, pct24h: 0, pct7d: 0, drawdownPct: 0, state: 'active', updatedAtMs: 1 },
        aiIntent: { intent: 'test', confidence: 1, strategies: ['flashloan_atomic'] },
        exposure: { activePct: 50, sandboxPct: 0, idlePct: 50, atRiskPct: 0 },
        alerts: [],
        allocations: [],
        capitalFlows: [],
        decisions: [],
        regime: { current: 'neutral', confidence: 0.5, history: [] },
        risk: { composite: 0, caps: { maxDailyLossPct: 1, maxExposurePct: 1, sandboxCapPct: 1, probationCapPct: 1 }, breakers: { drawdownBreaker: false, gasAnomalyBreaker: false, driftBreaker: false } },
        governance: { v1Focus: 'flashloan_atomic', aiAuthority: 'bounded', governanceEnabled: true, mutationEnabled: false, evolutionFrozen: true, allocationsFrozen: false, sandboxOnly: false, paused: false },
        governanceHistory: [],
        sandbox: { sandboxNavUsd: 0, probationTradesLeft: 0, proposals: [] },
        analytics: { equity: [], utilizationPct: 0, returnPerRisk: 0, execSuccessPct: 0, slippagePct: 0, complexityCost: 0 },
        observability: { loopMsP50: 1, rpcErrRate: 0, oppsSeen: 0, oppsExecutable: 0 },
        holdReasonCode: 'capital_truth_degraded',
        holdReasonCodes: ['capital_truth_degraded'],
        suggestedNextAction: 'restore_capital_truth',
    };
    node_assert_1.strict.deepEqual((0, command_1.commandCenterHoldReasonCodes)(snapshot), ['capital_truth_degraded']);
    node_assert_1.strict.equal((0, command_1.commandCenterHoldLine)(snapshot), 'capital truth degraded · next restore capital truth');
});
(0, node_test_1.default)('command center hold helpers fall back to launch then fund hold canon', () => {
    const snapshot = {
        ok: true,
        portfolio: { navUsd: 1000, pct24h: 0, pct7d: 0, drawdownPct: 0, state: 'active', updatedAtMs: 1 },
        aiIntent: { intent: 'test', confidence: 1, strategies: ['flashloan_atomic'] },
        exposure: { activePct: 50, sandboxPct: 0, idlePct: 50, atRiskPct: 0 },
        alerts: [],
        allocations: [],
        capitalFlows: [],
        decisions: [],
        regime: { current: 'neutral', confidence: 0.5, history: [] },
        risk: { composite: 0, caps: { maxDailyLossPct: 1, maxExposurePct: 1, sandboxCapPct: 1, probationCapPct: 1 }, breakers: { drawdownBreaker: false, gasAnomalyBreaker: false, driftBreaker: false } },
        governance: { v1Focus: 'flashloan_atomic', aiAuthority: 'bounded', governanceEnabled: true, mutationEnabled: false, evolutionFrozen: true, allocationsFrozen: false, sandboxOnly: false, paused: false },
        governanceHistory: [],
        sandbox: { sandboxNavUsd: 0, probationTradesLeft: 0, proposals: [] },
        analytics: { equity: [], utilizationPct: 0, returnPerRisk: 0, execSuccessPct: 0, slippagePct: 0, complexityCost: 0 },
        observability: { loopMsP50: 1, rpcErrRate: 0, oppsSeen: 0, oppsExecutable: 0 },
        fundSummary: {
            fundStage: 'private_fund',
            riskPosture: 'defensive',
            riskScore: 0.7,
            holdReasonCode: 'capital_truth_degraded',
            holdReasonCodes: ['capital_truth_degraded'],
            suggestedNextAction: 'restore_capital_truth',
        },
        launch: {
            currentLaunchMode: 'STAGED_MULTI_STRATEGY',
            activeFamilies: ['flashloan_atomic'],
            nextRecommendedFamily: '',
            blockedFamilies: {},
            blockedFamilyDetails: {},
            families: [],
            reasons: [],
            recommendation: {
                nextFamily: '',
                whyNow: [],
                whyNotOthers: {},
                whyNotOthersDetails: {},
                rollbackRecommendation: '',
                holdReasonCode: 'drawdown_hard_stop',
                holdReasonCodes: ['drawdown_hard_stop'],
                suggestedNextAction: 'reduce_drawdown_and_clear_hard_stop',
            },
        },
    };
    node_assert_1.strict.deepEqual((0, command_1.commandCenterHoldReasonCodes)(snapshot), ['drawdown_hard_stop']);
    node_assert_1.strict.equal((0, command_1.commandCenterHoldLine)(snapshot), 'drawdown hard stop · next reduce drawdown and clear hard stop');
});
(0, node_test_1.default)('command center recovery helpers prefer explicit top-level recovery canon and fall back to fund health', () => {
    const topLevel = {
        ok: true,
        portfolio: { navUsd: 1000, pct24h: 0, pct7d: 0, drawdownPct: 0, state: 'defensive', updatedAtMs: 1 },
        aiIntent: { intent: 'test', confidence: 1, strategies: ['flashloan_atomic'] },
        exposure: { activePct: 50, sandboxPct: 0, idlePct: 50, atRiskPct: 0 },
        alerts: [],
        allocations: [],
        capitalFlows: [],
        decisions: [],
        regime: { current: 'neutral', confidence: 0.5, history: [] },
        risk: { composite: 0, caps: { maxDailyLossPct: 1, maxExposurePct: 1, sandboxCapPct: 1, probationCapPct: 1 }, breakers: { drawdownBreaker: false, gasAnomalyBreaker: false, driftBreaker: false } },
        governance: { v1Focus: 'flashloan_atomic', aiAuthority: 'bounded', governanceEnabled: true, mutationEnabled: false, evolutionFrozen: true, allocationsFrozen: false, sandboxOnly: false, paused: false },
        governanceHistory: [],
        sandbox: { sandboxNavUsd: 0, probationTradesLeft: 0, proposals: [] },
        analytics: { equity: [], utilizationPct: 0, returnPerRisk: 0, execSuccessPct: 0, slippagePct: 0, complexityCost: 0 },
        observability: { loopMsP50: 1, rpcErrRate: 0, oppsSeen: 0, oppsExecutable: 0 },
        recoveryStatus: 'capital_truth_restore_required',
        recoveryReasonCode: 'capital_truth_unavailable',
        recoveryReasonCodes: ['capital_truth_unavailable'],
        recoveryNextAction: 'restore_capital_truth',
    };
    node_assert_1.strict.deepEqual((0, command_1.commandCenterRecoveryReasonCodes)(topLevel), ['capital_truth_unavailable']);
    node_assert_1.strict.equal((0, command_1.commandCenterRecoveryLine)(topLevel), 'capital truth unavailable · next restore capital truth');
    const fallback = {
        ...topLevel,
        recoveryStatus: undefined,
        recoveryReasonCode: undefined,
        recoveryReasonCodes: undefined,
        recoveryNextAction: undefined,
        fundSummary: {
            fundStage: 'private_fund',
            riskPosture: 'defensive',
            riskScore: 0.7,
            recoveryStatus: 'internal_prime_reconciliation_required',
            recoveryReasonCode: 'internal_prime_journal_borrowed_mismatch',
            recoveryReasonCodes: ['internal_prime_journal_borrowed_mismatch'],
            recoveryNextAction: 'repair_internal_prime_accounting',
        },
    };
    node_assert_1.strict.deepEqual((0, command_1.commandCenterRecoveryReasonCodes)(fallback), ['internal_prime_journal_borrowed_mismatch']);
    node_assert_1.strict.equal((0, command_1.commandCenterRecoveryLine)(fallback), 'internal prime journal borrowed mismatch · next repair internal prime accounting');
});
(0, node_test_1.default)('command center recovery freshness helpers prefer top-level canon and fall back to fund health', () => {
    const snapshot = {
        ok: true,
        portfolio: { navUsd: 1000, pct24h: 0, pct7d: 0, drawdownPct: 0, state: 'defensive', updatedAtMs: 1 },
        aiIntent: { intent: 'test', confidence: 1, strategies: ['flashloan_atomic'] },
        exposure: { activePct: 50, sandboxPct: 0, idlePct: 50, atRiskPct: 0 },
        alerts: [],
        allocations: [],
        capitalFlows: [],
        decisions: [],
        regime: { current: 'neutral', confidence: 0.5, history: [] },
        risk: { composite: 0, caps: { maxDailyLossPct: 1, maxExposurePct: 1, sandboxCapPct: 1, probationCapPct: 1 }, breakers: { drawdownBreaker: false, gasAnomalyBreaker: false, driftBreaker: false } },
        governance: { v1Focus: 'flashloan_atomic', aiAuthority: 'bounded', governanceEnabled: true, mutationEnabled: false, evolutionFrozen: true, allocationsFrozen: false, sandboxOnly: false, paused: false },
        governanceHistory: [],
        sandbox: { sandboxNavUsd: 0, probationTradesLeft: 0, proposals: [] },
        analytics: { equity: [], utilizationPct: 0, returnPerRisk: 0, execSuccessPct: 0, slippagePct: 0, complexityCost: 0 },
        observability: { loopMsP50: 1, rpcErrRate: 0, oppsSeen: 0, oppsExecutable: 0 },
        recoveryFreshnessClass: 'unavailable',
        recoveryFreshnessReasonCode: 'capital_truth_freshness_unavailable',
        recoveryFreshnessReasonCodes: ['capital_truth_freshness_unavailable'],
        recoveryFreshnessNextAction: 'refresh_capital_truth_snapshot',
    };
    node_assert_1.strict.equal((0, command_1.commandCenterRecoveryFreshnessLine)(snapshot), 'capital truth freshness unavailable · class unavailable · next refresh capital truth snapshot');
    const fallback = {
        ...snapshot,
        recoveryFreshnessClass: undefined,
        recoveryFreshnessReasonCode: undefined,
        recoveryFreshnessReasonCodes: undefined,
        recoveryFreshnessNextAction: undefined,
        fundSummary: {
            fundStage: 'private_fund',
            riskPosture: 'defensive',
            riskScore: 0.7,
            recoveryFreshnessClass: 'stale',
            recoveryFreshnessReasonCode: 'internal_prime_reconciliation_freshness_stale',
            recoveryFreshnessReasonCodes: ['internal_prime_reconciliation_freshness_stale'],
            recoveryFreshnessNextAction: 'refresh_internal_prime_reconciliation',
        },
    };
    node_assert_1.strict.equal((0, command_1.commandCenterRecoveryFreshnessLine)(fallback), 'internal prime reconciliation freshness stale · class stale · next refresh internal prime reconciliation');
});
(0, node_test_1.default)('command center recovery history line surfaces recovered capital truth state', () => {
    const snapshot = {
        ok: true,
        portfolio: { navUsd: 1000, pct24h: 0, pct7d: 0, drawdownPct: 0, state: 'defensive', updatedAtMs: 1 },
        aiIntent: { intent: 'test', confidence: 1, strategies: ['flashloan_atomic'] },
        exposure: { activePct: 50, sandboxPct: 0, idlePct: 50, atRiskPct: 0 },
        alerts: [], allocations: [], capitalFlows: [], decisions: [],
        regime: { current: 'neutral', confidence: 0.5, history: [] },
        risk: { composite: 0, caps: { maxDailyLossPct: 1, maxExposurePct: 1, sandboxCapPct: 1, probationCapPct: 1 }, breakers: { drawdownBreaker: false, gasAnomalyBreaker: false, driftBreaker: false } },
        governance: { v1Focus: 'flashloan_atomic', aiAuthority: 'bounded', governanceEnabled: true, mutationEnabled: false, evolutionFrozen: true, allocationsFrozen: false, sandboxOnly: false, paused: false },
        governanceHistory: [], sandbox: { sandboxNavUsd: 0, probationTradesLeft: 0, proposals: [] },
        analytics: { equity: [], utilizationPct: 0, returnPerRisk: 0, execSuccessPct: 0, slippagePct: 0, complexityCost: 0 },
        observability: { loopMsP50: 1, rpcErrRate: 0, oppsSeen: 0, oppsExecutable: 0 },
        recoveryHistoryComponent: 'capital_truth',
        recoveryHistoryStatus: 'recovered',
        recoveryRecoveredAtTsMs: 1700000060000,
    };
    node_assert_1.strict.match((0, command_1.commandCenterRecoveryHistoryLine)(snapshot), /recovered/);
    node_assert_1.strict.match((0, command_1.commandCenterRecoveryHistoryLine)(snapshot), /capital truth/);
});
(0, node_test_1.default)('command center recovery history line includes count, severity, and last healthy markers', () => {
    const snapshot = {
        ok: true,
        portfolio: { navUsd: 1000, pct24h: 0, pct7d: 0, drawdownPct: 0, state: 'defensive', updatedAtMs: 1 },
        aiIntent: { intent: 'test', confidence: 1, strategies: ['flashloan_atomic'] },
        exposure: { activePct: 50, sandboxPct: 0, idlePct: 50, atRiskPct: 0 },
        alerts: [], allocations: [], capitalFlows: [], decisions: [],
        regime: { current: 'neutral', confidence: 0.5, history: [] },
        risk: { composite: 0, caps: { maxDailyLossPct: 1, maxExposurePct: 1, sandboxCapPct: 1, probationCapPct: 1 }, breakers: { drawdownBreaker: false, gasAnomalyBreaker: false, driftBreaker: false } },
        governance: { v1Focus: 'flashloan_atomic', aiAuthority: 'bounded', governanceEnabled: true, mutationEnabled: false, evolutionFrozen: true, allocationsFrozen: false, sandboxOnly: false, paused: false },
        governanceHistory: [], sandbox: { sandboxNavUsd: 0, probationTradesLeft: 0, proposals: [] },
        analytics: { equity: [], utilizationPct: 0, returnPerRisk: 0, execSuccessPct: 0, slippagePct: 0, complexityCost: 0 },
        observability: { loopMsP50: 1, rpcErrRate: 0, oppsSeen: 0, oppsExecutable: 0 },
        recoveryHistoryComponent: 'capital_truth',
        recoveryHistoryStatus: 'degraded',
        recoveryDegradedCount: 3,
        recoveryLastHealthyTsMs: 1700000000000,
        recoveryDegradationSeverityClass: 'persistent',
    };
    const line = (0, command_1.commandCenterRecoveryHistoryLine)(snapshot);
    node_assert_1.strict.match(line, /count 3/);
    node_assert_1.strict.match(line, /severity persistent/);
    node_assert_1.strict.match(line, /last healthy/);
});
(0, node_test_1.default)('command center recovery reliability line surfaces fragile recovered state', () => {
    const snapshot = {
        ok: true,
        portfolio: { navUsd: 1000, pct24h: 0, pct7d: 0, drawdownPct: 0, state: 'defensive', updatedAtMs: 1 },
        aiIntent: { intent: 'hold', confidence: 0.9, strategies: ['flashloan_atomic'] },
        exposure: { activePct: 50, sandboxPct: 0, idlePct: 50, atRiskPct: 0 },
        alerts: [], allocations: [], capitalFlows: [], decisions: [],
        regime: { current: 'neutral', confidence: 0.5, history: [] },
        risk: { composite: 0, caps: { maxDailyLossPct: 1, maxExposurePct: 1, sandboxCapPct: 1, probationCapPct: 1 }, breakers: { drawdownBreaker: false, gasAnomalyBreaker: false, driftBreaker: false } },
        governance: { v1Focus: 'flashloan_atomic', aiAuthority: 'bounded', governanceEnabled: true, mutationEnabled: false, evolutionFrozen: true, allocationsFrozen: false, sandboxOnly: false, paused: false },
        governanceHistory: [], sandbox: { sandboxNavUsd: 0, probationTradesLeft: 0, proposals: [] },
        analytics: { equity: [], utilizationPct: 0, returnPerRisk: 0, execSuccessPct: 0, slippagePct: 0, complexityCost: 0 },
        observability: { loopMsP50: 1, rpcErrRate: 0, oppsSeen: 0, oppsExecutable: 0 },
        recoveryReliabilityClass: 'fragile',
        recoveryReliabilityReasonCode: 'recovery_reliability_fragile',
        recoveryReliabilityReasonCodes: ['recovery_reliability_fragile', 'recovery_recovered_fragile'],
        recoveryReliabilityNextAction: 'repair_internal_prime_accounting',
        recoveryRecoveredFragile: true,
    };
    const line = (0, command_1.commandCenterRecoveryReliabilityLine)(snapshot);
    node_assert_1.strict.match(line, /recovery reliability fragile/);
    node_assert_1.strict.match(line, /recovered fragile yes/);
    node_assert_1.strict.match(line, /repair internal prime accounting/);
});
(0, node_test_1.default)('command center execution advisory helper prefers explicit top-level advisory canon and falls back to fund reliability', () => {
    const topLevel = {
        ok: true,
        portfolio: { navUsd: 1000, pct24h: 0, pct7d: 0, drawdownPct: 0, state: 'defensive', updatedAtMs: 1 },
        aiIntent: { intent: 'test', confidence: 1, strategies: ['flashloan_atomic'] },
        exposure: { activePct: 50, sandboxPct: 0, idlePct: 50, atRiskPct: 0 },
        alerts: [], allocations: [], capitalFlows: [], decisions: [],
        regime: { current: 'neutral', confidence: 0.5, history: [] },
        risk: { composite: 0, caps: { maxDailyLossPct: 1, maxExposurePct: 1, sandboxCapPct: 1, probationCapPct: 1 }, breakers: { drawdownBreaker: false, gasAnomalyBreaker: false, driftBreaker: false } },
        governance: { v1Focus: 'flashloan_atomic', aiAuthority: 'bounded', governanceEnabled: true, mutationEnabled: false, evolutionFrozen: true, allocationsFrozen: false, sandboxOnly: false, paused: false },
        governanceHistory: [], sandbox: { sandboxNavUsd: 0, probationTradesLeft: 0, proposals: [] },
        analytics: { equity: [], utilizationPct: 0, returnPerRisk: 0, execSuccessPct: 0, slippagePct: 0, complexityCost: 0 },
        observability: { loopMsP50: 1, rpcErrRate: 0, oppsSeen: 0, oppsExecutable: 0 },
        executionAdvisoryActive: true,
        executionAdvisorySeverity: 'warning',
        executionAdvisoryClass: 'fragile',
        executionAdvisoryReasonCode: 'recovery_reliability_fragile',
        executionAdvisoryReasonCodes: ['recovery_reliability_fragile'],
        executionAdvisoryNextAction: 'repair_internal_prime_accounting',
    };
    node_assert_1.strict.equal((0, command_1.commandCenterExecutionAdvisoryLine)(topLevel), 'recovery reliability fragile · severity warning · class fragile · next repair internal prime accounting');
    const fallback = {
        ...topLevel,
        executionAdvisoryActive: undefined,
        executionAdvisorySeverity: undefined,
        executionAdvisoryClass: undefined,
        executionAdvisoryReasonCode: undefined,
        executionAdvisoryReasonCodes: undefined,
        executionAdvisoryNextAction: undefined,
        fundSummary: {
            fundStage: 'private_fund',
            riskPosture: 'defensive',
            riskScore: 0.7,
            recoveryReliabilityClass: 'fragile',
            recoveryReliabilityReasonCode: 'recovery_reliability_fragile',
            recoveryReliabilityReasonCodes: ['recovery_reliability_fragile'],
            recoveryReliabilityNextAction: 'repair_internal_prime_accounting',
        },
    };
    node_assert_1.strict.equal((0, command_1.commandCenterExecutionAdvisoryLine)(fallback), 'recovery reliability fragile · severity warning · class fragile · next repair internal prime accounting');
});
