import assert from 'node:assert/strict';
import test from 'node:test';
import {
  Reconciler,
  classifyReconciliationFreshness,
} from '../src/api/reconciliation';

test('reconciliation starts unavailable without a successful observation', () => {
  assert.equal(classifyReconciliationFreshness(10_000, {}), 'unavailable');
});

test('reconciliation freshness degrades before becoming stale', () => {
  assert.equal(classifyReconciliationFreshness(10_000, { lastSuccessAtMs: 9_000 }), 'fresh');
  assert.equal(classifyReconciliationFreshness(20_000, { lastSuccessAtMs: 10_000 }), 'degraded');
  assert.equal(classifyReconciliationFreshness(31_000, { lastSuccessAtMs: 10_000 }), 'stale');
});

test('authoritative polling replaces realtime state and records a canonical observation', () => {
  const reconciler = new Reconciler<{ value: number }>();
  assert.equal(reconciler.acceptRealtime({ value: 1 }, 100, 1_000), true);
  assert.equal(reconciler.acceptAuthoritative({ value: 2 }, 200, 2_000), true);

  const state = reconciler.snapshot(2_000);
  assert.deepEqual(state.value, { value: 2 });
  assert.equal(state.meta.lastSource, 'authoritative');
  assert.equal(state.meta.authoritativeVersion, 1);
  assert.equal(state.meta.realtimeVersion, 1);
});

test('older realtime observations cannot overwrite newer authoritative truth', () => {
  const reconciler = new Reconciler<{ value: number }>();
  assert.equal(reconciler.acceptAuthoritative({ value: 10 }, 500, 1_000), true);
  assert.equal(reconciler.acceptRealtime({ value: 9 }, 499, 1_100), false);

  const state = reconciler.snapshot(1_100);
  assert.deepEqual(state.value, { value: 10 });
  assert.equal(state.meta.authoritativeVersion, 1);
  assert.equal(state.meta.realtimeVersion, 0);
});

test('older realtime observations cannot overwrite newer realtime observations', () => {
  const reconciler = new Reconciler<{ value: number }>();
  assert.equal(reconciler.acceptRealtime({ value: 2 }, 200, 2_000), true);
  assert.equal(reconciler.acceptRealtime({ value: 1 }, 100, 3_000), false);
  assert.deepEqual(reconciler.snapshot(3_000).value, { value: 2 });
});

test('reconciliation becomes stale after the last successful source update', () => {
  const reconciler = new Reconciler<{ value: number }>();
  assert.equal(reconciler.acceptRealtime({ value: 1 }, 100, 1_000), true);
  assert.equal(reconciler.snapshot(8_000).freshness, 'fresh');
  assert.equal(reconciler.snapshot(15_000).freshness, 'degraded');
  assert.equal(reconciler.snapshot(22_001).freshness, 'stale');
});

test('errors do not erase the last known good value', () => {
  const reconciler = new Reconciler<{ value: number }>();
  reconciler.acceptAuthoritative({ value: 7 }, 100, 1_000);
  reconciler.recordError(new Error('backend unavailable'), 2_000);

  const state = reconciler.snapshot(2_000);
  assert.deepEqual(state.value, { value: 7 });
  assert.equal(state.meta.lastError, 'backend unavailable');
  assert.equal(state.freshness, 'fresh');
});
