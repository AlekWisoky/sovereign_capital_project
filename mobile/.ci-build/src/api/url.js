"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.buildWsUrl = exports.buildApiUrl = exports.normalizeBaseUrl = void 0;
function normalizeBaseUrl(baseUrl) {
    return String(baseUrl || '').trim().replace(/\/$/, '');
}
exports.normalizeBaseUrl = normalizeBaseUrl;
function buildApiUrl(baseUrl, path) {
    const base = normalizeBaseUrl(baseUrl);
    if (!base) {
        if (/^https?:\/\//i.test(path))
            return path;
        return path;
    }
    if (/^https?:\/\//i.test(path))
        return path;
    return `${base}${path.startsWith('/') ? path : `/${path}`}`;
}
exports.buildApiUrl = buildApiUrl;
function buildWsUrl(baseUrl, path) {
    const httpUrl = buildApiUrl(baseUrl, path);
    return httpUrl.replace(/^http/i, 'ws');
}
exports.buildWsUrl = buildWsUrl;
