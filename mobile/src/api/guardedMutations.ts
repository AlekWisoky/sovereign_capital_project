import {
  setSettings,
  setWealthGoal,
  tradeOpportunity,
  withdrawExecute,
  withdrawConfig,
  withdrawAllExecute,
  convertWithdrawExecute,
  saveRpcPreferences,
  setLaunchMode,
  enableNextFamily,
  pauseLaunchFamily,
  revertLaunchFamily,
  quarantineLaunchFamily,
  applyPreset,
  selectChain,
  type JsonObject,
  type OpportunityActionResult,
} from './client';
import { guardMutation, mutationKindForSettingsPatch, type MutationGuardContext } from './mutationGuard';
import {
  reconcileSubmittedExternalWalletTransaction,
  submitPreparedExternalWalletTransaction,
} from './offRampExternalWallet';
import type { PreparedOffRamp } from './offRampExternalWallet';
import { walletConnectState } from '../walletConnect/session';

export type GuardedMutationError = Error & { reasonCode?: string };

function denied(reasonCode: string): never {
  const error = new Error(`mutation_denied:${reasonCode}`) as GuardedMutationError;
  error.reasonCode = reasonCode;
  throw error;
}

function assertAllowed(kind: Parameters<typeof guardMutation>[0], context: MutationGuardContext): void {
  const result = guardMutation(kind, context);
  if (!result.allowed) denied(result.reasonCode);
}

async function externalWalletWithdraw(
  baseUrl: string,
  req: Record<string, unknown>,
  adminKey: string,
): Promise<JsonObject> {
  const session = walletConnectState();
  if (!session.connected || !session.address) denied('wallet_not_connected');
  const prepared = req.prepared as PreparedOffRamp | undefined;
  if (!prepared) denied('prepared_transaction_required');
  const submitted = await submitPreparedExternalWalletTransaction(prepared);
  const reconciled = await reconcileSubmittedExternalWalletTransaction(
    baseUrl,
    adminKey,
    prepared,
    submitted.txHash,
  );
  return {
    ...reconciled,
    tx_hash: submitted.txHash,
    submission_status: submitted.status,
    intent_id: submitted.intentId,
  } as JsonObject;
}

async function externalWalletConvertWithdraw(
  baseUrl: string,
  req: Record<string, unknown>,
  adminKey: string,
): Promise<JsonObject> {
  const session = walletConnectState();
  if (!session.connected || !session.address) denied('wallet_not_connected');
  const prepared = req.prepared as PreparedOffRamp | undefined;
  if (!prepared) denied('prepared_transaction_required');
  const submitted = await submitPreparedExternalWalletTransaction(prepared);
  const reconciled = await reconcileSubmittedExternalWalletTransaction(
    baseUrl,
    adminKey,
    prepared,
    submitted.txHash,
  );
  return {
    ...reconciled,
    tx_hash: submitted.txHash,
    submission_status: submitted.status,
    intent_id: submitted.intentId,
  } as JsonObject;
}

async function externalWalletMode(baseUrl: string, adminKey: string): Promise<boolean> {
  const config = await withdrawConfig(baseUrl, adminKey);
  return String(config.withdraw_mode ?? 'txdata') === 'txdata';
}

export async function guardedSetSettings(baseUrl: string, patch: Record<string, unknown>, adminKey: string, context: MutationGuardContext): Promise<JsonObject> {
  assertAllowed(mutationKindForSettingsPatch(patch), context);
  return setSettings(baseUrl, patch, adminKey);
}

export async function guardedSetWealthGoal(baseUrl: string, patch: Record<string, unknown>, adminKey: string, context: MutationGuardContext): Promise<JsonObject> {
  assertAllowed('settings', context);
  return setWealthGoal(baseUrl, patch, adminKey);
}

export async function guardedSaveRpcPreferences(baseUrl: string, body: Record<string, unknown>, adminKey: string, context: MutationGuardContext): Promise<JsonObject> {
  assertAllowed('settings', context);
  return saveRpcPreferences(baseUrl, body, adminKey);
}

export async function guardedTradeOpportunity(baseUrl: string, id: string, adminKey: string, context: MutationGuardContext, amountInOverride?: string): Promise<OpportunityActionResult> {
  assertAllowed('execution', context);
  return tradeOpportunity(baseUrl, id, adminKey, amountInOverride);
}

export async function guardedWithdrawExecute(baseUrl: string, req: Record<string, unknown>, adminKey: string, context: MutationGuardContext): Promise<JsonObject> {
  assertAllowed('withdrawal', context);
  if (await externalWalletMode(baseUrl, adminKey)) {
    return externalWalletWithdraw(baseUrl, req, adminKey);
  }
  return withdrawExecute(baseUrl, req, adminKey);
}

export async function guardedWithdrawAllExecute(baseUrl: string, req: Record<string, unknown>, adminKey: string, context: MutationGuardContext): Promise<JsonObject> {
  assertAllowed('withdrawal', context);
  return withdrawAllExecute(baseUrl, req, adminKey);
}

export async function guardedConvertWithdrawExecute(baseUrl: string, req: Record<string, unknown>, adminKey: string, context: MutationGuardContext): Promise<JsonObject> {
  assertAllowed('withdrawal', context);
  if (await externalWalletMode(baseUrl, adminKey)) {
    return externalWalletConvertWithdraw(baseUrl, req, adminKey);
  }
  return convertWithdrawExecute(baseUrl, req, adminKey);
}

export async function guardedSetLaunchMode(baseUrl: string, mode: string, adminKey: string, context: MutationGuardContext): Promise<JsonObject> {
  assertAllowed('launch_control', context);
  return setLaunchMode(baseUrl, mode, adminKey);
}

export async function guardedApplyPreset(baseUrl: string, chain: string, name: string, adminKey: string, context: MutationGuardContext): Promise<JsonObject> {
  assertAllowed('launch_control', context);
  return applyPreset(baseUrl, chain, name, adminKey);
}

export async function guardedEnableNextFamily(baseUrl: string, family: string | undefined, adminKey: string, context: MutationGuardContext): Promise<JsonObject> {
  assertAllowed('launch_control', context);
  return enableNextFamily(baseUrl, family, adminKey);
}

export async function guardedPauseLaunchFamily(baseUrl: string, family: string, adminKey: string, context: MutationGuardContext): Promise<JsonObject> {
  assertAllowed('launch_control', context);
  return pauseLaunchFamily(baseUrl, family, adminKey);
}

export async function guardedRevertLaunchFamily(baseUrl: string, family: string, adminKey: string, context: MutationGuardContext): Promise<JsonObject> {
  assertAllowed('launch_control', context);
  return revertLaunchFamily(baseUrl, family, adminKey);
}

export async function guardedQuarantineLaunchFamily(baseUrl: string, family: string, adminKey: string, context: MutationGuardContext, reasonCode?: string): Promise<JsonObject> {
  assertAllowed('launch_control', context);
  return quarantineLaunchFamily(baseUrl, family, reasonCode, adminKey);
}

export async function guardedSelectChain(baseUrl: string, chain: string, adminKey: string, context: MutationGuardContext): Promise<JsonObject> {
  assertAllowed('chain_control', context);
  return selectChain(baseUrl, chain, adminKey);
}
