import test from 'node:test';
import { strict as assert } from 'node:assert';

import { commandCenterExecutionAdvisoryLine, commandCenterHoldLine, commandCenterHoldReasonCodes, commandCenterRecoveryFreshnessLine, commandCenterRecoveryHistoryLine, commandCenterRecoveryLine, commandCenterRecoveryReasonCodes, commandCenterRecoveryReliabilityLine } from '../src/utils/command';
import type { CommandCenterSnapshot } from '../src/commandCenter/types';

test('command center hold helpers prefer explicit top-level hold canon', () => {
  const snapshot: CommandCenterSnapshot = {
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
  assert.deepEqual(commandCenterHoldReasonCodes(snapshot), ['capital_truth_degraded']);
  assert.equal(commandCenterHoldLine(snapshot), 'capital truth degraded · next restore capital truth');
});

test('command center hold helpers fall back to launch then fund hold canon', () => {
  const snapshot: CommandCenterSnapshot = {
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
  assert.deepEqual(commandCenterHoldReasonCodes(snapshot), ['drawdown_hard_stop']);
  assert.equal(commandCenterHoldLine(snapshot), 'drawdown hard stop · next reduce drawdown and clear hard stop');
});

test('command center recovery helpers prefer explicit top-level recovery canon and fall back to fund health', () => {
  const topLevel: CommandCenterSnapshot = {
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
  assert.deepEqual(commandCenterRecoveryReasonCodes(topLevel), ['capital_truth_unavailable']);
  assert.equal(commandCenterRecoveryLine(topLevel), 'capital truth unavailable · next restore capital truth');

  const fallback: CommandCenterSnapshot = {
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
  assert.deepEqual(commandCenterRecoveryReasonCodes(fallback), ['internal_prime_journal_borrowed_mismatch']);
  assert.equal(commandCenterRecoveryLine(fallback), 'internal prime journal borrowed mismatch · next repair internal prime accounting');
});


test('command center recovery freshness helpers prefer top-level canon and fall back to fund health', () => {
  const snapshot: CommandCenterSnapshot = {
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
  assert.equal(commandCenterRecoveryFreshnessLine(snapshot), 'capital truth freshness unavailable · class unavailable · next refresh capital truth snapshot');

  const fallback: CommandCenterSnapshot = {
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
  assert.equal(commandCenterRecoveryFreshnessLine(fallback), 'internal prime reconciliation freshness stale · class stale · next refresh internal prime reconciliation');
});


test('command center recovery history line surfaces recovered capital truth state', () => {
  const snapshot: CommandCenterSnapshot = {
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
  assert.match(commandCenterRecoveryHistoryLine(snapshot), /recovered/);
  assert.match(commandCenterRecoveryHistoryLine(snapshot), /capital truth/);
});


test('command center recovery history line includes count, severity, and last healthy markers', () => {
  const snapshot: CommandCenterSnapshot = {
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
  const line = commandCenterRecoveryHistoryLine(snapshot);
  assert.match(line, /count 3/);
  assert.match(line, /severity persistent/);
  assert.match(line, /last healthy/);
});


test('command center recovery reliability line surfaces fragile recovered state', () => {
  const snapshot: CommandCenterSnapshot = {
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
  const line = commandCenterRecoveryReliabilityLine(snapshot);
  assert.match(line, /recovery reliability fragile/);
  assert.match(line, /recovered fragile yes/);
  assert.match(line, /repair internal prime accounting/);
});


test('command center execution advisory helper prefers explicit top-level advisory canon and falls back to fund reliability', () => {
  const topLevel: CommandCenterSnapshot = {
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
  assert.equal(commandCenterExecutionAdvisoryLine(topLevel), 'recovery reliability fragile · severity warning · class fragile · next repair internal prime accounting');

  const fallback: CommandCenterSnapshot = {
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
  assert.equal(commandCenterExecutionAdvisoryLine(fallback), 'recovery reliability fragile · severity warning · class fragile · next repair internal prime accounting');
});
