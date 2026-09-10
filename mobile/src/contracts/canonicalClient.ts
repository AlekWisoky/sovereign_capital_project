import { normalizeBaseUrl } from "../api/url";
import type {
  CommandCenterCanonicalSnapshot,
  DecisionDetail,
  DeploymentInfo,
  FundLedgerProjection,
  WealthGoal,
} from "./canonical";

export type CanonicalRequestOptions = {
  adminKey?: string;
  signal?: AbortSignal;
};

function requestHeaders(adminKey?: string, json = false): Record<string, string> {
  return {
    ...(json ? { "content-type": "application/json" } : {}),
    ...(adminKey ? { "X-Admin-Key": adminKey } : {}),
  };
}

async function get<T>(baseUrl: string, path: string, options: CanonicalRequestOptions = {}): Promise<T> {
  const response = await fetch(`${normalizeBaseUrl(baseUrl)}${path}`, {
    headers: requestHeaders(options.adminKey),
    signal: options.signal,
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as T;
}

async function post<T>(
  baseUrl: string,
  path: string,
  body: unknown,
  options: CanonicalRequestOptions = {},
): Promise<T> {
  const response = await fetch(`${normalizeBaseUrl(baseUrl)}${path}`, {
    method: "POST",
    headers: requestHeaders(options.adminKey, true),
    body: JSON.stringify(body ?? {}),
    signal: options.signal,
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as T;
}

export async function getHealth(baseUrl: string, options?: CanonicalRequestOptions): Promise<Record<string, unknown>> {
  return await get<Record<string, unknown>>(baseUrl, "/health", options);
}

export async function getDeploymentInfo(baseUrl: string, options?: CanonicalRequestOptions): Promise<DeploymentInfo> {
  return await get<DeploymentInfo>(baseUrl, "/api/deploy/info", options);
}

export async function getCommandCenterSnapshot(
  baseUrl: string,
  options?: CanonicalRequestOptions,
): Promise<CommandCenterCanonicalSnapshot> {
  return await get<CommandCenterCanonicalSnapshot>(baseUrl, "/api/commandcenter/snapshot", options);
}

export async function getFundLedger(
  baseUrl: string,
  options?: CanonicalRequestOptions,
): Promise<FundLedgerProjection> {
  return await get<FundLedgerProjection>(baseUrl, "/api/fund/ledger", options);
}

export async function getWealthGoal(baseUrl: string, options?: CanonicalRequestOptions): Promise<WealthGoal> {
  return await get<WealthGoal>(baseUrl, "/api/wealth/goal", options);
}

export async function getXaiLatest(baseUrl: string, options?: CanonicalRequestOptions): Promise<Record<string, unknown>> {
  return await get<Record<string, unknown>>(baseUrl, "/api/xai/latest", options);
}

export async function getDecisionDetail(
  baseUrl: string,
  decisionId: string,
  options?: CanonicalRequestOptions,
): Promise<DecisionDetail> {
  return await get<DecisionDetail>(
    baseUrl,
    `/api/xai/decision/${encodeURIComponent(decisionId)}`,
    options,
  );
}

export async function getLaunchState(baseUrl: string, options?: CanonicalRequestOptions): Promise<Record<string, unknown>> {
  return await get<Record<string, unknown>>(baseUrl, "/api/launch/state", options);
}

export async function getReliabilityState(baseUrl: string, options?: CanonicalRequestOptions): Promise<Record<string, unknown>> {
  return await get<Record<string, unknown>>(baseUrl, "/api/reliability/state", options);
}

export async function getKdsState(baseUrl: string, options?: CanonicalRequestOptions): Promise<Record<string, unknown>> {
  return await get<Record<string, unknown>>(baseUrl, "/api/kds/state", options);
}

export async function setCommandCenterControls(
  baseUrl: string,
  body: { patch: Record<string, unknown>; reason: string },
  options?: CanonicalRequestOptions,
): Promise<Record<string, unknown>> {
  return await post<Record<string, unknown>>(baseUrl, "/api/commandcenter/control", body, options);
}

export async function getCommandCenterAudit(
  baseUrl: string,
  limit = 50,
  options?: CanonicalRequestOptions,
): Promise<{ ok?: boolean; items?: Array<Record<string, unknown>> }> {
  return await get<{ ok?: boolean; items?: Array<Record<string, unknown>> }>(
    baseUrl,
    `/api/commandcenter/audit/tail?limit=${encodeURIComponent(String(limit))}`,
    options,
  );
}
