"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const reconciliation_1 = require("../src/api/reconciliation");
const offRampExternalWallet_1 = require("../src/api/offRampExternalWallet");
const session_1 = require("../src/walletConnect/session");
const makeReconciler = () => new reconciliation_1.Reconciler();
(0, node_test_1.default)('reconciliation starts unavailable without a successful authoritative observation', () => {
    strict_1.default.equal((0, reconciliation_1.classifyReconciliationFreshness)(10000, {}), 'unavailable');
});
(0, node_test_1.default)('reconciliation freshness degrades before becoming stale', () => {
    strict_1.default.equal((0, reconciliation_1.classifyReconciliationFreshness)(10000, { lastAuthoritativeAtMs: 9000 }), 'fresh');
    strict_1.default.equal((0, reconciliation_1.classifyReconciliationFreshness)(20000, { lastAuthoritativeAtMs: 10000 }), 'degraded');
    strict_1.default.equal((0, reconciliation_1.classifyReconciliationFreshness)(31000, { lastAuthoritativeAtMs: 10000 }), 'stale');
});
(0, node_test_1.default)('authoritative polling establishes canonical truth after an advisory realtime observation', () => {
    const reconciler = makeReconciler();
    strict_1.default.equal(reconciler.acceptRealtime({ value: 1 }, 100, 1000), true);
    strict_1.default.equal(reconciler.acceptAuthoritative({ value: 2 }, 200, 2000), true);
    const state = reconciler.snapshot(2000);
    strict_1.default.deepEqual(state.value, { value: 2 });
    strict_1.default.deepEqual(state.advisoryValue, { value: 1 });
    strict_1.default.equal(state.meta.lastSource, 'authoritative');
    strict_1.default.equal(state.meta.authoritativeVersion, 1);
    strict_1.default.equal(state.meta.realtimeVersion, 1);
});
(0, node_test_1.default)('newer realtime observations never overwrite newer authoritative truth', () => {
    const reconciler = makeReconciler();
    strict_1.default.equal(reconciler.acceptAuthoritative({ value: 10 }, 500, 1000), true);
    strict_1.default.equal(reconciler.acceptRealtime({ value: 11 }, 600, 1100), true);
    const state = reconciler.snapshot(1100);
    strict_1.default.deepEqual(state.value, { value: 10 });
    strict_1.default.deepEqual(state.advisoryValue, { value: 11 });
    strict_1.default.equal(state.meta.authoritativeVersion, 1);
    strict_1.default.equal(state.meta.realtimeVersion, 1);
});
(0, node_test_1.default)('older realtime observations cannot overwrite newer realtime observations', () => {
    const reconciler = makeReconciler();
    strict_1.default.equal(reconciler.acceptRealtime({ value: 2 }, 200, 2000), true);
    strict_1.default.equal(reconciler.acceptRealtime({ value: 1 }, 100, 3000), false);
    strict_1.default.deepEqual(reconciler.snapshot(3000).advisoryValue, { value: 2 });
});
(0, node_test_1.default)('realtime does not make canonical truth fresh when authoritative polling is stale', () => {
    const reconciler = makeReconciler();
    strict_1.default.equal(reconciler.acceptAuthoritative({ value: 1 }, 100, 1000), true);
    strict_1.default.equal(reconciler.acceptRealtime({ value: 2 }, 200, 15000), true);
    strict_1.default.equal(reconciler.snapshot(15000).freshness, 'degraded');
    strict_1.default.equal(reconciler.snapshot(22001).freshness, 'stale');
});
(0, node_test_1.default)('errors do not erase the last known good canonical value', () => {
    const reconciler = makeReconciler();
    reconciler.acceptAuthoritative({ value: 7 }, 100, 1000);
    reconciler.recordError(new Error('backend unavailable'), 2000);
    const state = reconciler.snapshot(2000);
    strict_1.default.deepEqual(state.value, { value: 7 });
    strict_1.default.equal(state.meta.lastError, 'backend unavailable');
    strict_1.default.equal(state.freshness, 'fresh');
});
(0, node_test_1.default)('external-wallet prepared transaction binds the connected wallet when backend prepare is sender-agnostic', () => {
    const address = '0x1111111111111111111111111111111111111111';
    const provider = { request: async ({ method }) => method === 'eth_chainId' ? '0x1' : null };
    (0, session_1.setWalletConnectSession)({ provider, address, isConnected: true });
    const tx = (0, offRampExternalWallet_1.externalWalletTransactionFromPrepared)({
        ok: true,
        from_address: null,
        requested_from_address: null,
        tx: {
            to: '0x2222222222222222222222222222222222222222',
            data: '0x1234',
            value: '0x0',
            chainId: 1,
        },
    });
    strict_1.default.deepEqual(tx, {
        from: address,
        to: '0x2222222222222222222222222222222222222222',
        data: '0x1234',
        value: '0x0',
        chainId: '0x1',
    });
    (0, session_1.setWalletConnectSession)({ provider: null, address: null, isConnected: false });
});
(0, node_test_1.default)('external-wallet validation rejects a prepared sender different from the connected wallet', async () => {
    const connected = '0x1111111111111111111111111111111111111111';
    const prepared = '0x3333333333333333333333333333333333333333';
    const provider = { request: async ({ method }) => method === 'eth_chainId' ? '0x1' : null };
    (0, session_1.setWalletConnectSession)({ provider, address: connected, isConnected: true });
    const result = await (0, offRampExternalWallet_1.validatePreparedExternalWalletTransaction)({
        ok: true,
        from_address: prepared,
        tx: {
            to: '0x2222222222222222222222222222222222222222',
            data: '0x1234',
            value: '0x0',
            chainId: 1,
        },
    });
    strict_1.default.equal(result.ok, false);
    strict_1.default.equal(result.reasonCode, 'wallet_sender_mismatch');
    (0, session_1.setWalletConnectSession)({ provider: null, address: null, isConnected: false });
});
(0, node_test_1.default)('external-wallet validation rejects a connected wallet on the wrong chain', async () => {
    const address = '0x1111111111111111111111111111111111111111';
    const provider = { request: async ({ method }) => method === 'eth_chainId' ? '0x2' : null };
    (0, session_1.setWalletConnectSession)({ provider, address, isConnected: true });
    const result = await (0, offRampExternalWallet_1.validatePreparedExternalWalletTransaction)({
        ok: true,
        from_address: address,
        tx: {
            to: '0x2222222222222222222222222222222222222222',
            data: '0x1234',
            value: '0x0',
            chainId: 1,
        },
    });
    strict_1.default.equal(result.ok, false);
    strict_1.default.equal(result.reasonCode, 'wallet_chain_mismatch');
    (0, session_1.setWalletConnectSession)({ provider: null, address: null, isConnected: false });
});
(0, node_test_1.default)('external-wallet submission fails closed when no wallet is connected', async () => {
    (0, session_1.setWalletConnectSession)({ provider: null, address: null, isConnected: false });
    await strict_1.default.rejects((0, offRampExternalWallet_1.submitPreparedExternalWalletTransaction)({
        ok: true,
        from_address: '0x1111111111111111111111111111111111111111',
        tx: {
            to: '0x2222222222222222222222222222222222222222',
            data: '0x1234',
            value: '0x0',
            chainId: 1,
        },
    }), /external_wallet_wallet_not_connected/);
});
(0, node_test_1.default)('external-wallet submission rejects an invalid transaction hash from the wallet', async () => {
    const address = '0x1111111111111111111111111111111111111111';
    const provider = {
        request: async ({ method }) => {
            if (method === 'eth_chainId')
                return '0x1';
            if (method === 'eth_sendTransaction')
                return '0xdeadbeef';
            return null;
        },
    };
    (0, session_1.setWalletConnectSession)({ provider, address, isConnected: true });
    await strict_1.default.rejects((0, offRampExternalWallet_1.submitPreparedExternalWalletTransaction)({
        ok: true,
        from_address: address,
        tx: {
            to: '0x2222222222222222222222222222222222222222',
            data: '0x1234',
            value: '0x0',
            chainId: 1,
        },
    }), /Wallet returned an invalid transaction hash/);
    (0, session_1.setWalletConnectSession)({ provider: null, address: null, isConnected: false });
});
(0, node_test_1.default)('external-wallet submission returns the bound transaction and submitted status', async () => {
    const address = '0x1111111111111111111111111111111111111111';
    const transactionHash = `0x${'a'.repeat(64)}`;
    let sent;
    const provider = {
        request: async ({ method, params }) => {
            if (method === 'eth_chainId')
                return '0x1';
            if (method === 'eth_sendTransaction') {
                sent = params?.[0];
                return transactionHash;
            }
            return null;
        },
    };
    (0, session_1.setWalletConnectSession)({ provider, address, isConnected: true });
    const prepared = {
        ok: true,
        from_address: address,
        tx: {
            to: '0x2222222222222222222222222222222222222222',
            data: '0x1234',
            value: '0x0',
            chainId: 1,
        },
    };
    const result = await (0, offRampExternalWallet_1.submitPreparedExternalWalletTransaction)(prepared);
    strict_1.default.equal(result.txHash, transactionHash);
    strict_1.default.equal(result.status, 'submitted');
    strict_1.default.equal(result.intentId.length, 64);
    strict_1.default.deepEqual(result.transaction, {
        from: address,
        to: '0x2222222222222222222222222222222222222222',
        data: '0x1234',
        value: '0x0',
        chainId: '0x1',
    });
    strict_1.default.deepEqual(sent, {
        from: address,
        to: '0x2222222222222222222222222222222222222222',
        data: '0x1234',
        value: '0x0',
        chainId: '0x1',
    });
    (0, session_1.setWalletConnectSession)({ provider: null, address: null, isConnected: false });
});
(0, node_test_1.default)('external-wallet reconciliation uses the bound transaction after wallet disconnect', async () => {
    const transaction = { from: '0x1111111111111111111111111111111111111111', to: '0x2222222222222222222222222222222222222222', data: '0x1234', value: '0x0', chainId: '0x1' };
    let body;
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (_input, init) => {
        body = JSON.parse(String(init?.body));
        return new Response(JSON.stringify({ ok: true, settled: false }), { status: 200, headers: { 'content-type': 'application/json' } });
    };
    try {
        (0, session_1.setWalletConnectSession)({ provider: null, address: null, isConnected: false });
        const result = await (0, offRampExternalWallet_1.reconcileSubmittedExternalWalletTransaction)('https://example.test', 'admin-key', transaction, `0x${'a'.repeat(64)}`);
        strict_1.default.deepEqual(result, { ok: true, settled: false });
        strict_1.default.equal(body?.from_address, transaction.from);
        strict_1.default.equal(body?.to, transaction.to);
        strict_1.default.equal(body?.data, transaction.data);
        strict_1.default.equal(body?.value, transaction.value);
        strict_1.default.equal(body?.chain_id, transaction.chainId);
    }
    finally {
        globalThis.fetch = originalFetch;
    }
});
