"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.reconcileSubmittedExternalWalletTransaction = exports.submitPreparedExternalWalletTransaction = exports.validatePreparedExternalWalletTransaction = exports.externalWalletTransactionFromPrepared = exports.externalWalletIntentId = void 0;
const session_1 = require("../walletConnect/session");
const url_1 = require("./url");
function text(value) {
    return typeof value === 'string' ? value.trim() : value === undefined || value === null ? '' : String(value).trim();
}
function address(value) {
    return text(value).toLowerCase();
}
function isAddress(value) {
    return /^0x[0-9a-f]{40}$/.test(value.toLowerCase());
}
function hexData(value) {
    return /^0x[0-9a-f]*$/i.test(value) && value.length >= 4 && value.length % 2 === 0;
}
function normalizeChainId(value) {
    const raw = text(value);
    if (!raw)
        return '';
    try {
        if (/^0x[0-9a-f]+$/i.test(raw))
            return `0x${BigInt(raw).toString(16)}`;
        if (/^[0-9]+$/.test(raw))
            return `0x${BigInt(raw).toString(16)}`;
    }
    catch {
        return '';
    }
    return '';
}
function normalizeQuantity(value) {
    const raw = text(value);
    if (!raw)
        return '';
    try {
        if (/^0x[0-9a-f]+$/i.test(raw))
            return `0x${BigInt(raw).toString(16)}`;
        if (/^[0-9]+$/.test(raw))
            return `0x${BigInt(raw).toString(16)}`;
    }
    catch {
        return '';
    }
    return '';
}
function canonicalIntent(tx) {
    return JSON.stringify({
        chainId: tx.chainId,
        data: tx.data.toLowerCase(),
        from: tx.from.toLowerCase(),
        to: tx.to.toLowerCase(),
        value: tx.value,
    });
}
async function externalWalletIntentId(tx) {
    const bytes = new TextEncoder().encode(canonicalIntent(tx));
    const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(digest)).map((byte) => byte.toString(16).padStart(2, '0')).join('');
}
exports.externalWalletIntentId = externalWalletIntentId;
function externalWalletTransactionFromPrepared(prepared) {
    if (prepared.ok !== true || !prepared.tx)
        return null;
    const tx = prepared.tx;
    const to = address(tx.to);
    const data = text(tx.data);
    const value = normalizeQuantity(tx.value);
    const chainId = normalizeChainId(tx.chainId);
    const session = (0, session_1.walletConnectState)();
    const from = address(prepared.from_address) || address(prepared.requested_from_address) || address(session.address);
    if (!isAddress(to) || !isAddress(from) || !hexData(data) || value === '' || chainId === '')
        return null;
    return { from, to, data, value, chainId };
}
exports.externalWalletTransactionFromPrepared = externalWalletTransactionFromPrepared;
async function validatePreparedExternalWalletTransaction(prepared) {
    const session = (0, session_1.walletConnectState)();
    if (!session.connected || !isAddress(session.address)) {
        return { ok: false, reasonCode: 'wallet_not_connected' };
    }
    const tx = externalWalletTransactionFromPrepared(prepared);
    if (!tx)
        return { ok: false, reasonCode: 'invalid_prepared_tx' };
    if (address(session.address) !== tx.from) {
        return { ok: false, reasonCode: 'wallet_sender_mismatch' };
    }
    const provider = session.provider;
    if (!provider)
        return { ok: false, reasonCode: 'wallet_not_connected' };
    let chainId;
    try {
        chainId = normalizeChainId(await provider.request({ method: 'eth_chainId' }));
    }
    catch {
        return { ok: false, reasonCode: 'wallet_chain_unavailable' };
    }
    if (!chainId || chainId !== tx.chainId) {
        return { ok: false, reasonCode: 'wallet_chain_mismatch' };
    }
    return { ok: true, tx };
}
exports.validatePreparedExternalWalletTransaction = validatePreparedExternalWalletTransaction;
async function submitPreparedExternalWalletTransaction(prepared) {
    const validation = await validatePreparedExternalWalletTransaction(prepared);
    if (!validation.ok || !validation.tx) {
        throw new Error(`external_wallet_${validation.reasonCode ?? 'validation_failed'}`);
    }
    const transaction = validation.tx;
    const intentId = await externalWalletIntentId(transaction);
    const txHash = await (0, session_1.sendWalletConnectTransaction)(transaction);
    return { txHash, intentId, status: 'submitted', transaction };
}
exports.submitPreparedExternalWalletTransaction = submitPreparedExternalWalletTransaction;
async function reconcileSubmittedExternalWalletTransaction(baseUrl, adminKey, transaction, txHash) {
    if (!isAddress(transaction.from) || !isAddress(transaction.to) || !hexData(transaction.data) || !transaction.value || !transaction.chainId) {
        throw new Error('external_wallet_invalid_bound_transaction');
    }
    if (!/^0x[0-9a-fA-F]{64}$/.test(txHash))
        throw new Error('external_wallet_invalid_tx_hash');
    const intentId = await externalWalletIntentId(transaction);
    const response = await fetch(`${(0, url_1.normalizeBaseUrl)(baseUrl)}/api/withdraw/external/reconcile`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'X-Admin-Key': adminKey },
        body: JSON.stringify({
            intent_id: intentId,
            tx_hash: txHash,
            chain_id: transaction.chainId,
            from_address: transaction.from,
            to: transaction.to,
            data: transaction.data,
            value: transaction.value,
        }),
    });
    if (!response.ok)
        throw new Error(`HTTP ${response.status}`);
    return (await response.json());
}
exports.reconcileSubmittedExternalWalletTransaction = reconcileSubmittedExternalWalletTransaction;
