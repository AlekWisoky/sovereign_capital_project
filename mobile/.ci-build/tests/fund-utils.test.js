"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const node_assert_1 = require("node:assert");
const fund_1 = require("../src/utils/fund");
(0, node_test_1.default)('fund health hold helpers prefer explicit hold reason codes and next action', () => {
    const summary = {
        fundStage: 'private_fund',
        riskPosture: 'defensive',
        riskScore: 0.61,
        holdReasonCode: 'drawdown_hard_stop',
        holdReasonCodes: ['drawdown_hard_stop', 'kill_switch_active'],
        suggestedNextAction: 'reduce_drawdown_and_clear_hard_stop',
    };
    node_assert_1.strict.deepEqual((0, fund_1.fundHealthHoldReasonCodes)(summary), ['drawdown_hard_stop', 'kill_switch_active']);
    node_assert_1.strict.equal((0, fund_1.fundHealthHoldLine)(summary), 'drawdown hard stop · kill switch active · next reduce drawdown and clear hard stop');
});
(0, node_test_1.default)('fund health hold helpers fall back to single hold reason code', () => {
    const summary = {
        fundStage: 'pilot_capital',
        riskPosture: 'normal',
        riskScore: 0.2,
        holdReasonCode: 'capital_truth_degraded',
    };
    node_assert_1.strict.deepEqual((0, fund_1.fundHealthHoldReasonCodes)(summary), ['capital_truth_degraded']);
    node_assert_1.strict.equal((0, fund_1.fundHealthHoldLine)(summary), 'capital truth degraded');
});
(0, node_test_1.default)('fund health recovery reliability line surfaces fragile recovered state', () => {
    const summary = {
        fundStage: 'private_fund',
        riskPosture: 'defensive',
        riskScore: 0.61,
        recoveryReliabilityClass: 'fragile',
        recoveryReliabilityReasonCode: 'recovery_reliability_fragile',
        recoveryReliabilityReasonCodes: ['recovery_reliability_fragile', 'recovery_recovered_fragile'],
        recoveryReliabilityNextAction: 'repair_internal_prime_accounting',
        recoveryRecoveredFragile: true,
    };
    const line = (0, fund_1.fundHealthRecoveryReliabilityLine)(summary);
    node_assert_1.strict.match(line, /recovery reliability fragile/);
    node_assert_1.strict.match(line, /recovered fragile yes/);
    node_assert_1.strict.match(line, /repair internal prime accounting/);
});
