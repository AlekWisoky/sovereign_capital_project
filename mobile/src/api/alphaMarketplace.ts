import { apiGet } from './client';

export type AlphaMarketplaceItem = Record<string, any>;

export async function getAlphaMarketplace(baseUrl: string, adminKey?: string): Promise<{
  ok?: boolean;
  enabled?: boolean;
  contract?: Record<string, any>;
  items: AlphaMarketplaceItem[];
}> {
  const headers = adminKey ? { 'X-Admin-Key': adminKey } : undefined;
  const raw = await apiGet(baseUrl, '/api/fund/alpha-marketplace', headers);
  const value = raw && typeof raw === 'object' ? raw as Record<string, any> : {};
  return {
    ok: value.ok,
    enabled: value.enabled,
    contract: value.contract,
    items: Array.isArray(value.items) ? value.items : [],
  };
}
