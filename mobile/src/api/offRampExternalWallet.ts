import { walletConnectState, sendWalletConnectTransaction } from '../walletConnect/session';

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
): Promise<{ txHash: string; status: 'submitted' }> {
  const validation = await validatePreparedExternalWalletTransaction(prepared);
  if (!validation.ok || !validation.tx) {
    throw new Error(`external_wallet_${validation.reasonCode ?? 'validation_failed'}`);
  }

  const txHash = await sendWalletConnectTransaction(validation.tx);
  return { txHash, status: 'submitted' };
}
