"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const executionSummary_1 = require("../src/commandCenter/executionSummary");
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
};
const summary = (0, executionSummary_1.wealthGoalSummary)(snapshot);
strict_1.default.equal(summary.status, 'active');
strict_1.default.equal(summary.urgency, 'catch_up');
strict_1.default.equal(summary.nextGoalAllowed, false);
strict_1.default.equal(summary.riskScore, 0.33);
strict_1.default.equal(summary.nextGoalAggressivenessHint, 0.9);
strict_1.default.equal(summary.goalVelocityPctPerDay, 0.6);
strict_1.default.equal(summary.goalHorizonCompatibility, 0.75);
