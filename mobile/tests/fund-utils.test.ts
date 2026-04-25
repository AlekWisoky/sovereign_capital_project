import test from 'node:test';
import { strict as assert } from 'node:assert';

import { fundHealthHoldLine, fundHealthHoldReasonCodes, fundHealthRecoveryReliabilityLine } from '../src/utils/fund';
import type { FundHealthSummary } from '../src/commandCenter/types';

test('fund health hold helpers prefer explicit hold reason codes and next action', () => {
  const summary: FundHealthSummary = {
    fundStage: 'private_fund',
    riskPosture: 'defensive',
    riskScore: 0.61,
    holdReasonCode: 'drawdown_hard_stop',
    holdReasonCodes: ['drawdown_hard_stop', 'kill_switch_active'],
    suggestedNextAction: 'reduce_drawdown_and_clear_hard_stop',
  };
  assert.deepEqual(fundHealthHoldReasonCodes(summary), ['drawdown_hard_stop', 'kill_switch_active']);
  assert.equal(
    fundHealthHoldLine(summary),
    'drawdown hard stop · kill switch active · next reduce drawdown and clear hard stop',
  );
});

test('fund health hold helpers fall back to single hold reason code', () => {
  const summary: FundHealthSummary = {
    fundStage: 'pilot_capital',
    riskPosture: 'normal',
    riskScore: 0.2,
    holdReasonCode: 'capital_truth_degraded',
  };
  assert.deepEqual(fundHealthHoldReasonCodes(summary), ['capital_truth_degraded']);
  assert.equal(fundHealthHoldLine(summary), 'capital truth degraded');
});


test('fund health recovery reliability line surfaces fragile recovered state', () => {
  const summary: FundHealthSummary = {
    fundStage: 'private_fund',
    riskPosture: 'defensive',
    riskScore: 0.61,
    recoveryReliabilityClass: 'fragile',
    recoveryReliabilityReasonCode: 'recovery_reliability_fragile',
    recoveryReliabilityReasonCodes: ['recovery_reliability_fragile', 'recovery_recovered_fragile'],
    recoveryReliabilityNextAction: 'repair_internal_prime_accounting',
    recoveryRecoveredFragile: true,
  };
  const line = fundHealthRecoveryReliabilityLine(summary);
  assert.match(line, /recovery reliability fragile/);
  assert.match(line, /recovered fragile yes/);
  assert.match(line, /repair internal prime accounting/);
});
