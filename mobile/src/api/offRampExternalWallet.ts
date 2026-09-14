import { walletConnectState, sendWalletConnectTransaction } from '../walletConnect/session';
import { normalizeBaseUrl } from './url';

export type ExternalWalletTransaction = {
  from: string;
  to: string;
  data: string;
  value: string;
  chainId: string;
};

export type PreparedOffRamp = {
  ok?: boolean;
  from_address?: string | null;
  requested_from_address?: string | null;
  tx?: Record<string, unknown>;
};

export type ExternalWalletValidation = {
  ok: boolean;
  reasonCode?: string;
  tx?: ExternalWalletTransaction;
};

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : value === undefined || value === null ? '' : String(value).trim();
}

function address(value: unknown): string {
  return text(value).toLowerCase();
}

function isAddress(value: string): boolean {
  return /^0x[0-9a-f]{40}$/.test(value.toLowerCase());
}

function hexData(value: string): boolean {
  return /^0x[0-9a-f]*$/i.test(value) && value.length >= 4 && value.length % 2 === 0;
}

function normalizeChainId(value: unknown): string {
  const raw = text(value);
  if (!raw) return '';
  try {
    if (/^0x[0-9a-f]+$/i.test(raw)) return `0x${BigInt(raw).toString(16)}`;
    if (/^[0-9]+$/.test(raw)) return `0x${BigInt(raw).toString(16)}`;
  } catch {
    return '';
  }
  return '';
}

function normalizeQuantity(value: unknown): string {
  const raw = text(value);
  if (!raw) return '';
  try {
    if (/^0x[0-9a-f]+$/i.test(raw)) return `0x${BigInt(raw).toString(16)}`;
    if (/^[0-9]+$/.test(raw)) return `0x${BigInt(raw).toString(16)}`;
  } catch {
    return '';
  }
  return '';
}

function canonicalIntent(tx: ExternalWalletTransaction): string {
  return JSON.stringify({
    chainId: tx.chainId,
    from: tx.from.toLowerCase(),
    to: tx.to.toLowerCase(),
    data: tx.data.toLowerCase(),
    value: tx.value,
  });
}

export async function externalWalletIntentId(tx: ExternalWalletTransaction): Promise<string> {
  const bytes = new TextEncoder().encode(canonicalIntent(tx));
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest)).map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

export function externalWalletTransactionFromPrepared(
  prepared: PreparedOffRamp,
): ExternalWalletTransaction | null {
  if (prepared.ok !== true || !prepared.tx) return null;
  const tx = prepared.tx;
  const to = address(tx.to);
  const data = text(tx.data);
  const value = normalizeQuantity(tx.value);
  const chainId = normalizeChainId(tx.chainId);
  const from = address(prepared.from_address ?? prepared.requested_from_address);
  if (!isAddress(to) || !isAddress(from) || !hexData(data) || value === '' || chainId === '') return null;
  return { from, to, data, value, chainId };
}

export async function validatePreparedExternalWalletTransaction(
  prepared: PreparedOffRamp,
): Promise<ExternalWalletValidation> {
  const tx = externalWalletTransactionFromPrepared(prepared);
  if (!tx) return { ok: false, reasonCode: 'invalid_prepared_tx' };

  const session = walletConnectState();
  if (!session.connected || !isAddress(session.address)) {
    return { ok: false, reasonCode: 'wallet_not_connected' };
  }
  if (address(session.address) !== tx.from) {
    return { ok: false, reasonCode: 'wallet_sender_mismatch' };
  }

  const provider = session.provider;
  if (!provider) return { ok: false, reasonCode: 'wallet_not_connected' };
  let chainId: string;
  try {
    chainId = normalizeChainId(await provider.request({ method: 'eth_chainId' }));
  } catch {
    return { ok: false, reasonCode: 'wallet_chain_unavailable' };
  }
  if (!chainId || chainId !== tx.chainId) {
    return { ok: false, reasonCode: 'wallet_chain_mismatch' };
  }

  return { ok: true, tx };
}

export async function submitPreparedExternalWalletTransaction(
  prepared: PreparedOffRamp,
): Promise<{ txHash: string; intentId: string; status: 'submitted' }> {
  const validation = await validatePreparedExternalWalletTransaction(prepared);
  if (!validation.ok || !validation.tx) {
    throw new Error(`external_wallet_${validation.reasonCode ?? 'validation_failed'}`);
  }

  const intentId = await externalWalletIntentId(validation.tx);
  const txHash = await sendWalletConnectTransaction(validation.tx);
  return { txHash, intentId, status: 'submitted' };
}

export async function reconcileSubmittedExternalWalletTransaction(
  baseUrl: string,
  adminKey: string,
  prepared: PreparedOffRamp,
  txHash: string,
): Promise<Record<string, unknown>> {
  const validation = await validatePreparedExternalWalletTransaction(prepared);
  if (!validation.ok || !validation.tx) {
    throw new Error(`external_wallet_${validation.reasonCode ?? 'validation_failed'}`);
  }
  if (!/^0x[0-9a-fA-F]{64}$/.test(txHash)) throw new Error('external_wallet_invalid_tx_hash');
  const intentId = await externalWalletIntentId(validation.tx);
  const response = await fetch(`${normalizeBaseUrl(baseUrl)}/api/withdraw/external/reconcile`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'X-Admin-Key': adminKey },
    body: JSON.stringify({
      intent_id: intentId,
      tx_hash: txHash,
      chain_id: validation.tx.chainId,
      from_address: validation.tx.from,
      to: validation.tx.to,
      data: validation.tx.data,
      value: validation.tx.value,
    }),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as Record<string, unknown>;
}
