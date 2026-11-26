"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const node_assert_1 = require("node:assert");
const executionSummary_1 = require("../src/commandCenter/executionSummary");
const snap = {
    execution: {
        endpointQuality: {
            lanes: {
                PRIVATE: { endpoints: [{ endpoint: 'rpc-fast', score: 0.93, avg_latency_ms: 110, success_rate: 0.98 }], relays: [{ endpoint: 'relay-a', score: 0.91, avg_latency_ms: 95, success_rate: 0.99 }] },
            },
        },
        endpointUniverse: {
            private: { lane: 'PRIVATE', reason: 'operator_preferences', candidates: [{ url: 'rpc-fast', source: 'config', operator_preferred: true, privacy_class: 'public' }], relays: [{ url: 'relay-a', source: 'preferences', operator_preferred: true, privacy_class: 'private' }] },
        },
        routeQuality: {
            items: [
                { key: 'k1', route_family: 'flashloan_atomic', venue_subset: ['uni', 'curve'], split_signature: 'uni:0.5,curve:0.5', success_rate: 0.9, mean_realized_edge_usd: 6.2, quality: 0.94, pair: 'WETH/USDC', size_bucket: 'medium', latency_class: 'fast' },
            ],
        },
        liveExecution: {
            items: [
                { txHash: '0x1', routeFamily: 'flashloan_atomic', family: 'flashloan_atomic', lane: 'PRIVATE', endpoint: 'rpc-fast', fallbackReady: true, routeInvalidCauses: ['leg:curve:adversarial_fragile'], adversarial: { pendingCount: 4, interferenceProbability: 0.42, requiresPrivateLane: true }, flashloan: { selectedProvider: 'aave', providerPriority: ['aave'], reasonCodes: ['reserve_distortion'], providerChoiceReason: 'preferred_provider_selected', sizing: { size_mult: 1.2, borrow_mult: 1.3 } } },
            ],
        },
        killSwitch: {
            suppressions: {
                'family:flashloan_atomic': { reason_codes: ['fee_burn_rate'] },
            },
        },
    },
};
(0, node_test_1.default)('endpoint ranking rows prioritize highest score', () => {
    const rows = (0, executionSummary_1.endpointRankingRows)(snap);
    node_assert_1.strict.equal(rows[0]?.endpoint, 'rpc-fast');
    node_assert_1.strict.equal(rows[1]?.endpoint, 'relay-a');
});
(0, node_test_1.default)('endpoint universe rows flatten candidates and relays', () => {
    const rows = (0, executionSummary_1.endpointUniverseRows)(snap);
    node_assert_1.strict.equal(rows[0]?.reason, 'operator_preferences');
    node_assert_1.strict.equal(rows.some((r) => r.endpoint === 'relay-a'), true);
});
(0, node_test_1.default)('route quality rows expose quality and mean edge', () => {
    const rows = (0, executionSummary_1.routeQualityRows)(snap);
    node_assert_1.strict.equal(rows[0]?.quality, 0.94);
    node_assert_1.strict.equal(rows[0]?.meanEdgeUsd, 6.2);
    node_assert_1.strict.equal(rows[0]?.pair, 'WETH/USDC');
});
(0, node_test_1.default)('fragility summary surfaces private lane, pending count, invalid causes and provider', () => {
    const summary = (0, executionSummary_1.liveFragilitySummary)(snap);
    node_assert_1.strict.equal(summary.requiresPrivateLane, true);
    node_assert_1.strict.equal(summary.provider, 'aave');
    node_assert_1.strict.equal(summary.pendingCount, 4);
    node_assert_1.strict.equal(summary.routeInvalidCauses[0], 'leg:curve:adversarial_fragile');
    node_assert_1.strict.equal(summary.providerChoiceReason, 'preferred_provider_selected');
    node_assert_1.strict.equal(summary.borrowMult, 1.3);
});
(0, node_test_1.default)('kill switch reasons flatten suppression map', () => {
    const reasons = (0, executionSummary_1.killSwitchReasons)(snap);
    node_assert_1.strict.equal(reasons.some((r) => r.includes('fee_burn_rate')), true);
});
