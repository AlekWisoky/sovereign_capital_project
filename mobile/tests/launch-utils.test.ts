import test from 'node:test';
import { strict as assert } from 'node:assert';

import { familyDependencyRows, launchRecoveryFreshnessLine, launchRecoveryHistoryLine, launchRecoveryLine, launchRecoveryReliabilityLine, launchRollbackText, launchStatusLabel, launchWhyNow, launchWhyNotLines, launchWhyNotOverflowCount, launchWhyNotPreview } from '../src/utils/launch';
import type { FamilyReadiness, LaunchSummary } from '../src/commandCenter/types';

const family: FamilyReadiness = {
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

test('launch status label prefers ready state', () => {
  assert.equal(launchStatusLabel(family), 'Ready');
  assert.equal(familyDependencyRows(family).every((x) => x.ok), true);
});

test('launch recommendation helpers prefer explicit recommendation', () => {
  const summary: LaunchSummary = {
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
  assert.equal(JSON.stringify(launchWhyNow(summary)), JSON.stringify(['stable_readiness', 'capital_ready']));
  assert.equal(launchRollbackText(summary), 'revert_to_v1_learning');
  assert.equal(JSON.stringify(launchWhyNotLines(summary)), JSON.stringify([
    'mev search = internal prime journal borrowed mismatch · next repair internal prime accounting',
  ]));
  assert.equal(JSON.stringify(launchWhyNotPreview(summary, 1)), JSON.stringify([
    'mev search = internal prime journal borrowed mismatch · next repair internal prime accounting',
  ]));
  assert.equal(launchWhyNotOverflowCount(summary, 1), 0);
});

test('launch why-not preview truncates and reports overflow deterministically', () => {
  const summary: LaunchSummary = {
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

  assert.equal(JSON.stringify(launchWhyNotPreview(summary, 2)), JSON.stringify([
    'mev search = internal prime journal borrowed mismatch · next repair internal prime accounting',
    'liquidations = capital truth degraded · next restore capital truth',
  ]));
  assert.equal(launchWhyNotOverflowCount(summary, 2), 1);
});


test('launch why-now falls back to hold reason codes when rollout is blocked', () => {
  const summary: LaunchSummary = {
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
  assert.equal(JSON.stringify(launchWhyNow(summary)), JSON.stringify(['drawdown_hard_stop']));
});


test('launch recovery line prefers explicit recovery canon and falls back to top-level launch recovery', () => {
  const blockedSummary: LaunchSummary = {
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
  assert.equal(launchRecoveryLine(blockedSummary), 'capital truth unavailable · next restore capital truth');

  const topLevelRecovery: LaunchSummary = {
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
  assert.equal(launchRecoveryLine(topLevelRecovery), 'internal prime journal borrowed mismatch · next repair internal prime accounting');
});


test('launch recovery freshness line prefers explicit freshness canon and falls back to top-level launch recovery freshness', () => {
  const blockedSummary: LaunchSummary = {
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
  assert.equal(launchRecoveryFreshnessLine(blockedSummary), 'capital truth freshness unavailable · class unavailable · next refresh capital truth snapshot');

  const topLevelRecovery: LaunchSummary = {
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
  assert.equal(launchRecoveryFreshnessLine(topLevelRecovery), 'internal prime reconciliation freshness stale · class stale · next refresh internal prime reconciliation');
});


test('launch recovery history line surfaces degraded capital truth state', () => {
  const summary: LaunchSummary = {
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
  assert.match(launchRecoveryHistoryLine(summary), /degraded/);
  assert.match(launchRecoveryHistoryLine(summary), /capital truth/);
});


test('launch recovery history line includes count, severity, and last healthy markers', () => {
  const summary: LaunchSummary = {
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
  const line = launchRecoveryHistoryLine(summary);
  assert.match(line, /count 4/);
  assert.match(line, /severity persistent/);
  assert.match(line, /last healthy/);
});


test('launch recovery reliability line surfaces fragile recovered state', () => {
  const summary: LaunchSummary = {
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
  const line = launchRecoveryReliabilityLine(summary);
  assert.match(line, /recovery reliability fragile/);
  assert.match(line, /recovered fragile yes/);
  assert.match(line, /restore capital truth/);
});
