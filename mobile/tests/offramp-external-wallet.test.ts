import assert from 'node:assert/strict';
import test from 'node:test';
import { setWalletConnectSession } from '../src/walletConnect/session';
import {
  externalWalletIntentId,
  externalWalletTransactionFromPrepared,
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

function provider(chainId: unknown = '0x1') {
  return {
    request: async ({ method }: { method: string }) => {
      if (method === 'eth_chainId') return chainId;
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
