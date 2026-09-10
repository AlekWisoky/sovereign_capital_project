import {
  setSettings,
  tradeOpportunity,
  withdrawExecute,
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

export async function guardedSetSettings(
  baseUrl: string,
  patch: Record<string, unknown>,
  adminKey: string,
  context: MutationGuardContext,
): Promise<JsonObject> {
  assertAllowed(mutationKindForSettingsPatch(patch), context);
  return setSettings(baseUrl, patch, adminKey);
}

export async function guardedSaveRpcPreferences(
  baseUrl: string,
  body: Record<string, unknown>,
  adminKey: string,
  context: MutationGuardContext,
): Promise<JsonObject> {
  assertAllowed('settings', context);
  return saveRpcPreferences(baseUrl, body, adminKey);
}

export async function guardedTradeOpportunity(
  baseUrl: string,
  id: string,
  adminKey: string,
  context: MutationGuardContext,
  amountInOverride?: string,
): Promise<OpportunityActionResult> {
  assertAllowed('execution', context);
  return tradeOpportunity(baseUrl, id, adminKey, amountInOverride);
}

export async function guardedWithdrawExecute(
  baseUrl: string,
  req: Record<string, unknown>,
  adminKey: string,
  context: MutationGuardContext,
): Promise<JsonObject> {
  assertAllowed('withdrawal', context);
  return withdrawExecute(baseUrl, req, adminKey);
}

export async function guardedWithdrawAllExecute(
  baseUrl: string,
  req: Record<string, unknown>,
  adminKey: string,
  context: MutationGuardContext,
): Promise<JsonObject> {
  assertAllowed('withdrawal', context);
  return withdrawAllExecute(baseUrl, req, adminKey);
}

export async function guardedConvertWithdrawExecute(
  baseUrl: string,
  req: Record<string, unknown>,
  adminKey: string,
  context: MutationGuardContext,
): Promise<JsonObject> {
  assertAllowed('withdrawal', context);
  return convertWithdrawExecute(baseUrl, req, adminKey);
}

export async function guardedSetLaunchMode(
  baseUrl: string,
  mode: string,
  adminKey: string,
  context: MutationGuardContext,
): Promise<JsonObject> {
  assertAllowed('launch_control', context);
  return setLaunchMode(baseUrl, mode, adminKey);
}

export async function guardedApplyPreset(
  baseUrl: string,
  chain: string,
  name: string,
  adminKey: string,
  context: MutationGuardContext,
): Promise<JsonObject> {
  assertAllowed('launch_control', context);
  return applyPreset(baseUrl, chain, name, adminKey);
}

export async function guardedEnableNextFamily(
  baseUrl: string,
  family: string | undefined,
  adminKey: string,
  context: MutationGuardContext,
): Promise<JsonObject> {
  assertAllowed('launch_control', context);
  return enableNextFamily(baseUrl, family, adminKey);
}

export async function guardedPauseLaunchFamily(
  baseUrl: string,
  family: string,
  adminKey: string,
  context: MutationGuardContext,
): Promise<JsonObject> {
  assertAllowed('launch_control', context);
  return pauseLaunchFamily(baseUrl, family, adminKey);
}

export async function guardedRevertLaunchFamily(
  baseUrl: string,
  family: string,
  adminKey: string,
  context: MutationGuardContext,
): Promise<JsonObject> {
  assertAllowed('launch_control', context);
  return revertLaunchFamily(baseUrl, family, adminKey);
}

export async function guardedQuarantineLaunchFamily(
  baseUrl: string,
  family: string,
  adminKey: string,
  context: MutationGuardContext,
  reasonCode?: string,
): Promise<JsonObject> {
  assertAllowed('launch_control', context);
  return quarantineLaunchFamily(baseUrl, family, reasonCode, adminKey);
}

export async function guardedSelectChain(
  baseUrl: string,
  chain: string,
  adminKey: string,
  context: MutationGuardContext,
): Promise<JsonObject> {
  assertAllowed('chain_control', context);
  return selectChain(baseUrl, chain, adminKey);
}
