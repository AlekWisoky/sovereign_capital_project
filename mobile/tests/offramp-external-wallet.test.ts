import assert from 'node:assert/strict';
import test from 'node:test';
import { setWalletConnectSession } from '../src/walletConnect/session';
import {
  externalWalletIntentId,
  externalWalletTransactionFromPrepared,
  submitPreparedExternalWalletTransaction,
  validatePreparedExternalWalletTransaction,
} from '../src/api/offRampExternalWallet';

const ADDRESS = '0x1111111111111111111111111111111111111111';
const OTHER_ADDRESS = '0x2222222222222222222222222222222222222222';
const TO = '0x3333333333333333333333333333333333333333';
const DATA = '0x12345678';

function prepared(overrides: Record<string, unknown> = {}) {
  return {
    ok: true,
    from_address: ADDRESS,
    tx: {
      to: TO,
      data: DATA,
      value: '0x0',
      chainId: '1',
      ...overrides,
    },
  };
}

function provider(chainId: unknown = '0x1', sent: Record<string, unknown>[] = []) {
  return {
    request: async ({ method, params }: { method: string; params?: unknown[] }) => {
      if (method === 'eth_chainId') return chainId;
      if (method === 'eth_sendTransaction') {
        sent.push((params?.[0] ?? {}) as Record<string, unknown>);
        return '0x' + 'ab'.repeat(32);
      }
      throw new Error(`unexpected method:${method}`);
    },
  };
}

test.afterEach(() => {
  setWalletConnectSession({ provider: null, address: '', isConnected: false, open: null });
});

test('missing wallet is rejected before signing', async () => {
  const result = await validatePreparedExternalWalletTransaction(prepared());
  assert.deepEqual(result, { ok: false, reasonCode: 'wallet_not_connected' });
});

test('connected wallet sender mismatch is rejected', async () => {
  setWalletConnectSession({ provider: provider(), address: OTHER_ADDRESS, isConnected: true });
  const result = await validatePreparedExternalWalletTransaction(prepared());
  assert.deepEqual(result, { ok: false, reasonCode: 'wallet_sender_mismatch' });
});

test('wallet chain mismatch is rejected', async () => {
  setWalletConnectSession({ provider: provider('0x89'), address: ADDRESS, isConnected: true });
  const result = await validatePreparedExternalWalletTransaction(prepared());
  assert.deepEqual(result, { ok: false, reasonCode: 'wallet_chain_mismatch' });
});

test('malformed prepared transaction fields are rejected', async () => {
  assert.equal(externalWalletTransactionFromPrepared(prepared({ data: 'not-calldata' })), null);
  assert.equal(externalWalletTransactionFromPrepared(prepared({ to: OTHER_ADDRESS.slice(0, -1) })), null);
  assert.equal(externalWalletTransactionFromPrepared(prepared({ chainId: 'bogus' })), null);
});

test('valid prepared intent passes signer and chain validation without changing fields', async () => {
  setWalletConnectSession({ provider: provider(), address: ADDRESS, isConnected: true });
  const result = await validatePreparedExternalWalletTransaction(prepared());
  assert.equal(result.ok, true);
  assert.deepEqual(result.tx, {
    from: ADDRESS,
    to: TO,
    data: DATA,
    value: '0x0',
    chainId: '0x1',
  });
});

test('intent id is deterministic for the exact normalized transaction', async () => {
  const tx = externalWalletTransactionFromPrepared(prepared());
  assert.ok(tx);
  const first = await externalWalletIntentId(tx);
  const second = await externalWalletIntentId({ ...tx, chainId: '1' });
  assert.equal(first, second);
  assert.match(first, /^[0-9a-f]{64}$/);
});

test('submission sends the exact prepared transaction and returns submission evidence', async () => {
  const sent: Record<string, unknown>[] = [];
  setWalletConnectSession({ provider: provider('0x1', sent), address: ADDRESS, isConnected: true });
  const result = await submitPreparedExternalWalletTransaction(prepared());
  assert.equal(result.status, 'submitted');
  assert.match(result.txHash, /^0x[0-9a-f]{64}$/);
  assert.deepEqual(sent, [{
    from: ADDRESS,
    to: TO,
    data: DATA,
    value: '0x0',
    chainId: '0x1',
  }]);
});
