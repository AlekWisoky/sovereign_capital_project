import test from 'node:test';
import { strict as assert } from 'node:assert';

import { chooseFocusedFamily, nextWizardStep, previousWizardStep, sortFamiliesForOperator } from '../src/state/launchStore';
import type { FamilyReadiness, LaunchSummary } from '../src/commandCenter/types';

const active: FamilyReadiness = {
  family: 'flash_arb',
  score: 0.95,
  ready: true,
  status: 'eligible',
  reasons: [],
  blockers: [],
  count: 20,
  successRate: 0.9,
  gasEfficiency: 3,
  calibrationQuality: 1,
  stageAllowed: true,
  active: true,
  rolloutIndex: 0,
};

const pending: FamilyReadiness = {
  family: 'funding_arb',
  score: 0.8,
  ready: true,
  status: 'eligible',
  reasons: [],
  blockers: [],
  count: 8,
  successRate: 0.8,
  gasEfficiency: 1,
  calibrationQuality: 0.9,
  stageAllowed: true,
  active: false,
  rolloutIndex: 1,
};

test('wizard step helpers stay bounded', () => {
  assert.equal(previousWizardStep(0), 0);
  assert.equal(nextWizardStep(99), 4);
});

test('focused family chooses recommendation before fallback', () => {
  const summary: LaunchSummary = {
    currentLaunchMode: 'V1_ONLY',
    activeFamilies: ['flash_arb'],
    nextRecommendedFamily: 'funding_arb',
    blockedFamilies: {},
    families: [active, pending],
    reasons: [],
  };
  assert.equal(chooseFocusedFamily(summary), 'funding_arb');
  assert.equal(sortFamiliesForOperator([pending, active])[0].family, 'flash_arb');
});
