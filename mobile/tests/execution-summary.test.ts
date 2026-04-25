
import test from 'node:test';
import { strict as assert } from 'node:assert';
import type { CommandCenterSnapshot } from '../src/commandCenter/types';
import { endpointRankingRows, endpointUniverseRows, liveFragilitySummary, routeQualityRows, killSwitchReasons } from '../src/commandCenter/executionSummary';

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
} as unknown as CommandCenterSnapshot;

test('endpoint ranking rows prioritize highest score', () => {
  const rows = endpointRankingRows(snap);
  assert.equal(rows[0]?.endpoint, 'rpc-fast');
  assert.equal(rows[1]?.endpoint, 'relay-a');
});

test('endpoint universe rows flatten candidates and relays', () => {
  const rows = endpointUniverseRows(snap);
  assert.equal(rows[0]?.reason, 'operator_preferences');
  assert.equal(rows.some((r: any) => r.endpoint === 'relay-a'), true);
});

test('route quality rows expose quality and mean edge', () => {
  const rows = routeQualityRows(snap);
  assert.equal(rows[0]?.quality, 0.94);
  assert.equal(rows[0]?.meanEdgeUsd, 6.2);
  assert.equal(rows[0]?.pair, 'WETH/USDC');
});

test('fragility summary surfaces private lane, pending count, invalid causes and provider', () => {
  const summary = liveFragilitySummary(snap);
  assert.equal(summary.requiresPrivateLane, true);
  assert.equal(summary.provider, 'aave');
  assert.equal(summary.pendingCount, 4);
  assert.equal(summary.routeInvalidCauses[0], 'leg:curve:adversarial_fragile');
  assert.equal((summary as any).providerChoiceReason, 'preferred_provider_selected');
  assert.equal((summary as any).borrowMult, 1.3);
});

test('kill switch reasons flatten suppression map', () => {
  const reasons = killSwitchReasons(snap);
  assert.equal(reasons.some((r) => r.includes('fee_burn_rate')), true);
});
