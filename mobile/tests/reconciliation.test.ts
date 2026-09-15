import assert from 'node:assert/strict';
import test from 'node:test';
import {
  Reconciler,
  classifyReconciliationFreshness,
} from '../src/api/reconciliation';
import {
  reconcileSubmittedExternalWalletTransaction,
  submitPreparedExternalWalletTransaction,
  validatePreparedExternalWalletTransaction,
  type PreparedOffRamp,
} from '../src/api/offRampExternalWallet';
import { setWalletConnectSession } from '../src/walletConnect/session';

type TestState = { value: number };

const makeReconciler = () => new Reconciler<TestState>();

const prepared = (overrides: Record<string, unknown> = {}): PreparedOffRamp => ({
  ok: true,
  from_address: '0x1111111111111111111111111111111111111111',
  tx: {
    to: '0x2222222222222222222222222222222222222222',
    data: '0x1234',
    value: '0x0',
    chainId: '0x1',
    ...overrides,
  },
});

const connectedProvider = (chainId = '0x1', result: unknown = '0x' + 'a'.repeat(64)) => ({
  request: async ({ method }: { method: string }) => {
    if (method === 'eth_chainId') return chainId;
    if (method === 'eth_sendTransaction') return result;
    throw new Error(`unexpected_method:${method}`);
  },
});

const connect = (address = '0x1111111111111111111111111111111111111111', chainId = '0x1', result?: unknown) => {
  setWalletConnectSession({
    provider: connectedProvider(chainId, result),
    address,
    isConnected: true,
  });
};

const disconnect = () => setWalletConnectSession({ provider: null, address: '', isConnected: false });

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

test('external OffRamp rejects connected wallet sender mismatch before signing', async () => {
  connect('0x3333333333333333333333333333333333333333');
  const result = await validatePreparedExternalWalletTransaction(prepared());
  assert.deepEqual(result, { ok: false, reasonCode: 'wallet_sender_mismatch' });
  disconnect();
});

test('external OffRamp rejects connected wallet chain mismatch before signing', async () => {
  connect(undefined, '0x2');
  const result = await validatePreparedExternalWalletTransaction(prepared());
  assert.deepEqual(result, { ok: false, reasonCode: 'wallet_chain_mismatch' });
  disconnect();
});

test('external OffRamp rejects malformed prepared transaction fields before signing', async () => {
  connect();
  const result = await validatePreparedExternalWalletTransaction(prepared({ data: '0x123' }));
  assert.deepEqual(result, { ok: false, reasonCode: 'invalid_prepared_tx' });
  disconnect();
});

test('external OffRamp rejects missing external wallet before signing', async () => {
  disconnect();
  const result = await validatePreparedExternalWalletTransaction(prepared());
  assert.deepEqual(result, { ok: false, reasonCode: 'wallet_not_connected' });
});

test('external OffRamp rejects an invalid wallet transaction hash', async () => {
  connect(undefined, '0x1', 'not-a-tx-hash');
  await assert.rejects(
    () => submitPreparedExternalWalletTransaction(prepared()),
    /invalid transaction hash/i,
  );
  disconnect();
});

test('external OffRamp records submission evidence and reconciles to pending state', async () => {
  const txHash = '0x' + 'b'.repeat(64);
  connect(undefined, '0x1', txHash);
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => new Response(JSON.stringify({
    ok: true,
    status: 'pending',
    tx_hash: txHash,
    settled: false,
    submission_evidence: true,
    settlement_truth: false,
  }), { status: 200, headers: { 'content-type': 'application/json' } })) as typeof fetch;
  try {
    const submitted = await submitPreparedExternalWalletTransaction(prepared());
    assert.equal(submitted.txHash, txHash);
    assert.equal(submitted.status, 'submitted');
    const reconciled = await reconcileSubmittedExternalWalletTransaction(
      'https://example.invalid',
      'test-admin-key',
      prepared(),
      txHash,
    );
    assert.equal(reconciled.status, 'pending');
    assert.equal(reconciled.settled, false);
    assert.equal(reconciled.submission_evidence, true);
    assert.equal(reconciled.settlement_truth, false);
  } finally {
    globalThis.fetch = originalFetch;
    disconnect();
  }
});
