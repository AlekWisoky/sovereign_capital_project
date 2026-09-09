import { apiGet, apiPost, type JsonObject } from './client';

/** Canonical OMAR control surface. OMAR never owns decision identity. */
export async function omarState(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return (await apiGet(baseUrl, '/api/omar/state', adminKey ? { 'X-Admin-Key': adminKey } : undefined)) as JsonObject;
}

export async function omarStart(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return (await apiPost(baseUrl, '/api/omar/start', {}, adminKey ? { 'X-Admin-Key': adminKey } : undefined)) as JsonObject;
}

export async function omarStop(baseUrl: string, adminKey?: string): Promise<JsonObject> {
  return (await apiPost(baseUrl, '/api/omar/stop', {}, adminKey ? { 'X-Admin-Key': adminKey } : undefined)) as JsonObject;
}
