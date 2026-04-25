import assert from 'node:assert/strict';
import { wealthGoalSummary } from '../src/commandCenter/executionSummary';

const snapshot = {
  wealthGoal: {
    targetReturnPct: 12,
    timeframeDays: 21,
    riskTolerance: 'moderate',
    progressPct: 55,
    goalAchieved: false,
    goalStatus: 'active',
    goalUrgency: 'catch_up',
    nextGoalAllowed: false,
    nextGoalBlockedReasons: ['drawdown_near_goal_limit'],
    capitalBaseUsd: 5000,
    executionRealismScore: 0.8,
    stabilityScore: 0.76,
    riskScore: 0.33,
    nextGoalAggressivenessHint: 0.9,
    goalVelocityPctPerDay: 0.6,
    requiredVelocityPctPerDay: 0.8,
    goalHorizonCompatibility: 0.75,
    explanation: { why_posture: 'steady because realism is bounded' },
  },
} as any;

const summary = wealthGoalSummary(snapshot);
assert.equal(summary.status, 'active');
assert.equal(summary.urgency, 'catch_up');
assert.equal(summary.nextGoalAllowed, false);
assert.equal(summary.riskScore, 0.33);
assert.equal(summary.nextGoalAggressivenessHint, 0.9);

assert.equal(summary.goalVelocityPctPerDay, 0.6);
assert.equal(summary.goalHorizonCompatibility, 0.75);
