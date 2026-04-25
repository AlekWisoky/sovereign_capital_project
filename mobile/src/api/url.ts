export function normalizeBaseUrl(baseUrl: string): string {
  return String(baseUrl || '').trim().replace(/\/$/, '');
}

export function buildApiUrl(baseUrl: string, path: string): string {
  const base = normalizeBaseUrl(baseUrl);
  if (!base) {
    if (/^https?:\/\//i.test(path)) return path;
    return path;
  }
  if (/^https?:\/\//i.test(path)) return path;
  return `${base}${path.startsWith('/') ? path : `/${path}`}`;
}

export function buildWsUrl(baseUrl: string, path: string): string {
  const httpUrl = buildApiUrl(baseUrl, path);
  return httpUrl.replace(/^http/i, 'ws');
}
