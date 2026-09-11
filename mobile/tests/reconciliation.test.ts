import assert from 'node:assert/strict';
import test from 'node:test';
import {
  Reconciler,
  classifyReconciliationFreshness,
} from '../src/api/reconciliation';

type TestState = { value: number };

const makeReconciler = () => new Reconciler<TestState>();

test('reconciliation starts unavailable without a successful authoritative observation', () => {
  assert.equal(classifyReconciliationFreshness(10_000, {}), 'unavailable');
});

test('reconciliation freshness degrades before becoming stale', () => {
  assert.equal(classifyReconciliationFreshness(10_000, { lastAuthoritativeAtMs: 9_000 }), 'fresh');
  assert.equal(classifyReconciliationFreshness(20_000, { lastAuthoritativeAtMs: 10_000 }), 'degraded');
  assert.equal(classifyReconciliationFreshness(31_000, { lastAuthoritativeAtMs: 10_000 }), 'stale');
});

test('authoritative polling establishes canonical truth after an advisory realtime observation', () => {
  const reconciler = makeReconciler();
  assert.equal(reconciler.acceptRealtime({ value: 1 }, 100, 1_000), true);
  assert.equal(reconciler.acceptAuthoritative({ value: 2 }, 200, 2_000), true);

  const state = reconciler.snapshot(2_000);
  assert.deepEqual(state.value, { value: 2 });
  assert.deepEqual(state.advisoryValue, { value: 1 });
  assert.equal(state.meta.lastSource, 'authoritative');
  assert.equal(state.meta.authoritativeVersion, 1);
  assert.equal(state.meta.realtimeVersion, 1);
});

test('newer realtime observations never overwrite newer authoritative truth', () => {
  const reconciler = makeReconciler();
  assert.equal(reconciler.acceptAuthoritative({ value: 10 }, 500, 1_000), true);
  assert.equal(reconciler.acceptRealtime({ value: 11 }, 600, 1_100), true);

  const state = reconciler.snapshot(1_100);
  assert.deepEqual(state.value, { value: 10 });
  assert.deepEqual(state.advisoryValue, { value: 11 });
  assert.equal(state.meta.authoritativeVersion, 1);
  assert.equal(state.meta.realtimeVersion, 1);
});

test('older realtime observations cannot overwrite newer realtime observations', () => {
  const reconciler = makeReconciler();
  assert.equal(reconciler.acceptRealtime({ value: 2 }, 200, 2_000), true);
  assert.equal(reconciler.acceptRealtime({ value: 1 }, 100, 3_000), false);
  assert.deepEqual(reconciler.snapshot(3_000).advisoryValue, { value: 2 });
});

test('realtime does not make canonical truth fresh when authoritative polling is stale', () => {
  const reconciler = makeReconciler();
  assert.equal(reconciler.acceptAuthoritative({ value: 1 }, 100, 1_000), true);
  assert.equal(reconciler.acceptRealtime({ value: 2 }, 200, 15_000), true);
  assert.equal(reconciler.snapshot(15_000).freshness, 'degraded');
  assert.equal(reconciler.snapshot(22_001).freshness, 'stale');
});

test('errors do not erase the last known good canonical value', () => {
  const reconciler = makeReconciler();
  reconciler.acceptAuthoritative({ value: 7 }, 100, 1_000);
  reconciler.recordError(new Error('backend unavailable'), 2_000);

  const state = reconciler.snapshot(2_000);
  assert.deepEqual(state.value, { value: 7 });
  assert.equal(state.meta.lastError, 'backend unavailable');
  assert.equal(state.freshness, 'fresh');
});
