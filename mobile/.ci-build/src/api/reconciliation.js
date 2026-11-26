"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Reconciler = exports.classifyReconciliationFreshness = exports.DEFAULT_RECONCILIATION_THRESHOLDS = void 0;
exports.DEFAULT_RECONCILIATION_THRESHOLDS = {
    freshMs: 8000,
    staleMs: 20000,
};
function finite(value) {
    return typeof value === 'number' && Number.isFinite(value);
}
function observedTimestamp(raw, fallback) {
    return finite(raw) ? raw : fallback;
}
function classifyReconciliationFreshness(nowMs, meta, thresholds = exports.DEFAULT_RECONCILIATION_THRESHOLDS) {
    if (!finite(meta.lastAuthoritativeAtMs))
        return 'unavailable';
    const ageMs = Math.max(0, nowMs - meta.lastAuthoritativeAtMs);
    if (ageMs <= thresholds.freshMs)
        return 'fresh';
    if (ageMs <= thresholds.staleMs)
        return 'degraded';
    return 'stale';
}
exports.classifyReconciliationFreshness = classifyReconciliationFreshness;
class Reconciler {
    constructor(thresholds = exports.DEFAULT_RECONCILIATION_THRESHOLDS, initial, nowMs = Date.now()) {
        this.thresholds = thresholds;
        this.state = {
            value: initial,
            meta: {
                authoritativeVersion: 0,
                realtimeVersion: 0,
            },
            freshness: initial === undefined ? 'unavailable' : 'fresh',
        };
        if (initial !== undefined)
            this.state.meta.lastAuthoritativeAtMs = nowMs;
    }
    snapshot(nowMs = Date.now()) {
        return {
            value: this.state.value,
            advisoryValue: this.state.advisoryValue,
            meta: { ...this.state.meta },
            freshness: classifyReconciliationFreshness(nowMs, this.state.meta, this.thresholds),
        };
    }
    acceptAuthoritative(value, observedTsMs, receivedAtMs = Date.now()) {
        const observed = observedTimestamp(observedTsMs, receivedAtMs);
        const currentObserved = this.state.meta.authoritativeObservedTsMs;
        if (finite(currentObserved) && observed < currentObserved)
            return false;
        this.state.value = value;
        this.state.meta = {
            ...this.state.meta,
            lastAuthoritativeAtMs: receivedAtMs,
            lastSuccessAtMs: receivedAtMs,
            authoritativeObservedTsMs: observed,
            authoritativeVersion: this.state.meta.authoritativeVersion + 1,
            lastSource: 'authoritative',
            lastError: undefined,
        };
        this.state.freshness = 'fresh';
        return true;
    }
    acceptRealtime(value, observedTsMs, receivedAtMs = Date.now()) {
        const observed = observedTimestamp(observedTsMs, receivedAtMs);
        const currentRealtimeObserved = this.state.meta.realtimeObservedTsMs;
        if (finite(currentRealtimeObserved) && observed < currentRealtimeObserved)
            return false;
        this.state.advisoryValue = value;
        this.state.meta = {
            ...this.state.meta,
            lastRealtimeAtMs: receivedAtMs,
            realtimeObservedTsMs: observed,
            realtimeVersion: this.state.meta.realtimeVersion + 1,
            lastSource: 'realtime',
            lastError: undefined,
        };
        // Realtime never becomes canonical and never refreshes canonical freshness.
        this.state.freshness = classifyReconciliationFreshness(receivedAtMs, this.state.meta, this.thresholds);
        return true;
    }
    recordError(error, receivedAtMs = Date.now()) {
        this.state.meta = {
            ...this.state.meta,
            lastErrorAtMs: receivedAtMs,
            lastError: error instanceof Error ? error.message : String(error),
        };
        this.state.freshness = classifyReconciliationFreshness(receivedAtMs, this.state.meta, this.thresholds);
    }
}
exports.Reconciler = Reconciler;
