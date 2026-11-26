"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const node_assert_1 = require("node:assert");
const launchStore_1 = require("../src/state/launchStore");
const active = {
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
const pending = {
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
(0, node_test_1.default)('wizard step helpers stay bounded', () => {
    node_assert_1.strict.equal((0, launchStore_1.previousWizardStep)(0), 0);
    node_assert_1.strict.equal((0, launchStore_1.nextWizardStep)(99), 4);
});
(0, node_test_1.default)('focused family chooses recommendation before fallback', () => {
    const summary = {
        currentLaunchMode: 'V1_ONLY',
        activeFamilies: ['flash_arb'],
        nextRecommendedFamily: 'funding_arb',
        blockedFamilies: {},
        families: [active, pending],
        reasons: [],
    };
    node_assert_1.strict.equal((0, launchStore_1.chooseFocusedFamily)(summary), 'funding_arb');
    node_assert_1.strict.equal((0, launchStore_1.sortFamiliesForOperator)([pending, active])[0].family, 'flash_arb');
});
