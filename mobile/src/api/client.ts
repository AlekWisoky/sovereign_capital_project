import type { RuntimeState, JsonValue } from "../utils/types";
import { normalizeBaseUrl } from "./url";

export type JsonObject = { [k: string]: JsonValue };

function headers(adminKey?: string): Record<string, string> {
  const h: Record<string, string> = {};
  if (adminKey) h["X-Admin-Key"] = adminKey;
  return h;
}

// Low-level helpers used by the Sovereign Command Center layer.
// Additive exports: existing screen API calls remain unchanged.
export async function apiGet(baseUrl: string, path: string, extraHeaders?: Record<string, string>): Promise<unknown> {
  const url = `${normalizeBaseUrl(baseUrl)}${path}`;
  const r = await fetch(url, { headers: { ...(extraHeaders ?? {}) } });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return (await r.json()) as unknown;
}

export async function apiPost(baseUrl: string, path: string, body: unknown, extraHeaders?: Record<string, string>): Promise<unknown> {
  const url = `${normalizeBaseUrl(baseUrl)}${path}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json", ...(extraHeaders ?? {}) },
    body: JSON.stringify(body ?? {}),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return (await r.json()) as unknown;
}

async function jget<T>(url: string, adminKey?: string): Promise<T> {
  const r = await fetch(url, { headers: headers(adminKey) });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return (await r.json()) as T;
}

async function jpost<T>(url: string, body: unknown, adminKey?: string): Promise<T> {
  const h: Record<string, string> = { "content-type": "application/json", ...headers(adminKey) };
  const r = await fetch(url, { method: "POST", headers: h, body: JSON.stringify(body ?? {}) });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return (await r.json()) as T;
}

// -------------------------
// Core
// -------------------------
export async function health(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/health`, adminKey);
}

export async function deployInfo(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/deploy/info`, adminKey);
}

export async function fetchState(baseUrl: string, adminKey?: string): Promise<RuntimeState> {
  return await jget<RuntimeState>(`${normalizeBaseUrl(baseUrl)}/api/state`, adminKey);
}

export async function startRuntime(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/runtime/start`, {}, adminKey);
}

export async function stopRuntime(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/runtime/stop`, {}, adminKey);
}

export async function setSettings(baseUrl: string, patch: Record<string, unknown>, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/settings`, patch, adminKey);
}

export async function setSafety(baseUrl: string, patch: Record<string, unknown>, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/safety`, patch, adminKey);
}

export type OpportunityActionResult = {
  ok?: boolean;
  dry_run?: boolean;
  reason?: string;
  tx_hash?: string;
} & JsonObject;

export async function tradeOpportunity(baseUrl: string, id: string, adminKey?: string, amountInOverride?: string): Promise<OpportunityActionResult> {
  const body: Record<string, unknown> = { id };
  if (amountInOverride !== undefined && amountInOverride !== null) body.amount_in_override = String(amountInOverride);
  return await jpost<OpportunityActionResult>(`${normalizeBaseUrl(baseUrl)}/api/opportunities/trade`, body, adminKey);
}

export async function simulateOpportunity(baseUrl: string, id: string, adminKey?: string, amountInOverride?: string): Promise<OpportunityActionResult> {
  const body: Record<string, unknown> = { id };
  if (amountInOverride !== undefined && amountInOverride !== null) body.amount_in_override = String(amountInOverride);
  return await jpost<OpportunityActionResult>(`${normalizeBaseUrl(baseUrl)}/api/opportunities/simulate`, body, adminKey);
}

export async function adminState(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/admin/state`, adminKey);
}

export async function gasPresets(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/gas/presets`, adminKey);
}

export async function pnlSummary(baseUrl: string, window: number = 50, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/pnl/summary?window=${window}`, adminKey);
}

export async function pnlIncome(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/pnl/income`, adminKey);
}

// -------------------------
// Presets / chain switching
// -------------------------
export async function listPresets(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/presets`, adminKey);
}

export async function getPreset(baseUrl: string, chain: string, name: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/presets/${chain}/${name}`, adminKey);
}

export async function applyPreset(baseUrl: string, chain: string, name: string, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/presets/apply`, { chain, name, auto_start: true }, adminKey);
}

// -------------------------
// Multi-chain (additive)
// -------------------------

export type ChainsResponse = { ok?: boolean; active?: string; chains?: string[] } & JsonObject;

export async function fetchChains(baseUrl: string): Promise<ChainsResponse> {
  return await jget<ChainsResponse>(`${normalizeBaseUrl(baseUrl)}/api/multichain/chains`);
}

export async function selectChain(baseUrl: string, chain: string, adminKey?: string): Promise<ChainsResponse> {
  return await jpost<ChainsResponse>(`${normalizeBaseUrl(baseUrl)}/api/multichain/select`, { chain }, adminKey);
}

export async function multichainState(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/multichain/state`, adminKey);
}

export async function multichainSummary(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/multichain/summary`, adminKey);
}

export async function multichainSettings(baseUrl: string, patch: Record<string, unknown>, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/multichain/settings`, patch, adminKey);
}

// -------------------------
// Withdraw (executor)
// -------------------------
export async function withdrawConfig(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/withdraw/config`, adminKey);
}

export async function withdrawPrepare(baseUrl: string, req: Record<string, unknown>, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/withdraw/prepare`, req, adminKey);
}

export async function withdrawExecute(baseUrl: string, req: Record<string, unknown>, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/withdraw/execute`, req, adminKey);
}


export async function withdrawAllState(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/withdraw/all/state`, adminKey);
}

export async function withdrawAllConfig(baseUrl: string, req: Record<string, unknown>, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/withdraw/all/config`, req, adminKey);
}

export async function withdrawAllPreview(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/withdraw/all/preview`, {}, adminKey);
}

export async function withdrawAllExecute(baseUrl: string, req: Record<string, unknown>, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/withdraw/all/execute`, req, adminKey);
}

// -------------------------
// Convert + Withdraw (executor)
// -------------------------

export async function convertWithdrawQuote(baseUrl: string, req: Record<string, unknown>, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/withdraw/convert/quote`, req, adminKey);
}

export async function convertWithdrawPrepare(baseUrl: string, req: Record<string, unknown>, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/withdraw/convert/prepare`, req, adminKey);
}

export async function convertWithdrawExecute(baseUrl: string, req: Record<string, unknown>, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/withdraw/convert/execute`, req, adminKey);
}

// -------------------------
// Observability / analytics (read-only)
// -------------------------
export async function consensusState(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/consensus/state`, adminKey);
}

export async function behaveagentState(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/behaveagent/state`, adminKey);
}

export async function treasuryState(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/treasury/state`, adminKey);
}

export async function fetchTreasuryGoal(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/treasury/goal`, adminKey);
}

export async function setTreasuryGoal(baseUrl: string, patch: Record<string, unknown>, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/treasury/goal`, patch, adminKey);
}


export async function fetchWealthGoal(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/wealth/goal`, adminKey);
}

export async function setWealthGoal(baseUrl: string, patch: Record<string, unknown>, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/wealth/goal`, patch, adminKey);
}

export async function exportRftEpisodes(baseUrl: string, req: Record<string, unknown>, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/rft/episodes/export`, req, adminKey);
}

export async function metaCandidates(baseUrl: string, limit = 10, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/meta/candidates?limit=${encodeURIComponent(String(limit))}`, adminKey);
}

export async function metaApply(baseUrl: string, id: string, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/meta/apply`, { id }, adminKey);
}

export async function stressEvaluate(baseUrl: string, scenario: string, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/stress/evaluate`, { scenario }, adminKey);
}

export async function sampleRftEpisodes(baseUrl: string, limit = 5, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/rft/episodes/sample?limit=${encodeURIComponent(String(limit))}`, adminKey);
}

export async function replayBundle(baseUrl: string, eventId: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/rft/replay/bundle/${encodeURIComponent(eventId)}`, adminKey);
}

export async function verifyReplay(baseUrl: string, body: Record<string, unknown>, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/rft/replay/verify`, body, adminKey);
}

export async function governanceState(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/governance/state`, adminKey);
}

export async function blockspaceState(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/blockspace/state`, adminKey);
}

export async function analyticsDashboards(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/analytics/dashboards`, adminKey);
}

export async function txReceipt(baseUrl: string, txHash: string, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/tx/receipt`, { tx_hash: txHash }, adminKey);
}


export async function rpcPreferences(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/system/rpc/preferences`, adminKey);
}

export async function saveRpcPreferences(baseUrl: string, body: Record<string, unknown>, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/system/rpc/preferences`, body, adminKey);
}

export async function executionQuality(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/system/execution/quality`, adminKey);
}


export async function launchState(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/launch/state`, adminKey);
}

export async function setLaunchMode(baseUrl: string, mode: string, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/launch/mode`, { mode }, adminKey);
}

export async function enableNextFamily(baseUrl: string, family?: string, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/launch/enable-next`, family ? { family } : {}, adminKey);
}

export async function pauseLaunchFamily(baseUrl: string, family: string, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/launch/pause-family`, { family }, adminKey);
}


export async function revertLaunchFamily(baseUrl: string, family: string, adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/launch/revert-family`, { family }, adminKey);
}

export async function quarantineLaunchFamily(baseUrl: string, family: string, reasonCode = 'operator_quarantine', adminKey?: string): Promise<JsonObject> {
  return await jpost<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/launch/quarantine-family`, { family, reason_code: reasonCode }, adminKey);
}

export async function launchFamilyDetail(baseUrl: string, family: string, adminKey?: string): Promise<JsonObject> {
  return await jget<JsonObject>(`${normalizeBaseUrl(baseUrl)}/api/launch/family/${encodeURIComponent(family)}`, adminKey);
}
