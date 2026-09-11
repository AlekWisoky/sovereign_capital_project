export type ReconciliationSource = 'authoritative' | 'realtime';
export type ReconciliationFreshness = 'fresh' | 'degraded' | 'stale' | 'unavailable';

export type ReconciliationThresholds = {
  freshMs: number;
  staleMs: number;
};

export type ReconciliationMeta = {
  lastAuthoritativeAtMs?: number;
  lastRealtimeAtMs?: number;
  lastSuccessAtMs?: number;
  lastErrorAtMs?: number;
  authoritativeObservedTsMs?: number;
  realtimeObservedTsMs?: number;
  authoritativeVersion: number;
  realtimeVersion: number;
  lastSource?: ReconciliationSource;
  lastError?: string;
};

export type ReconciliationState<T> = {
  value?: T;
  meta: ReconciliationMeta;
  freshness: ReconciliationFreshness;
};

export const DEFAULT_RECONCILIATION_THRESHOLDS: ReconciliationThresholds = {
  freshMs: 8_000,
  staleMs: 20_000,
};

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function observedTimestamp(raw: unknown, fallback: number): number {
  return finite(raw) ? raw : fallback;
}

export function classifyReconciliationFreshness(
  nowMs: number,
  meta: Pick<ReconciliationMeta, 'lastSuccessAtMs'>,
  thresholds: ReconciliationThresholds = DEFAULT_RECONCILIATION_THRESHOLDS,
): ReconciliationFreshness {
  if (!finite(meta.lastSuccessAtMs)) return 'unavailable';
  const ageMs = Math.max(0, nowMs - meta.lastSuccessAtMs);
  if (ageMs <= thresholds.freshMs) return 'fresh';
  if (ageMs <= thresholds.staleMs) return 'degraded';
  return 'stale';
}

export class Reconciler<T> {
  private state: ReconciliationState<T>;
  private readonly thresholds: ReconciliationThresholds;

  constructor(
    thresholds: ReconciliationThresholds = DEFAULT_RECONCILIATION_THRESHOLDS,
    initial?: T,
    nowMs: number = Date.now(),
  ) {
    this.thresholds = thresholds;
    this.state = {
      value: initial,
      meta: {
        authoritativeVersion: 0,
        realtimeVersion: 0,
      },
      freshness: initial === undefined ? 'unavailable' : 'fresh',
    };
    if (initial !== undefined) this.state.meta.lastSuccessAtMs = nowMs;
  }

  snapshot(nowMs: number = Date.now()): ReconciliationState<T> {
    return {
      value: this.state.value,
      meta: { ...this.state.meta },
      freshness: classifyReconciliationFreshness(nowMs, this.state.meta, this.thresholds),
    };
  }

  acceptAuthoritative(
    value: T,
    observedTsMs?: number,
    receivedAtMs: number = Date.now(),
  ): boolean {
    const observed = observedTimestamp(observedTsMs, receivedAtMs);
    const currentObserved = this.state.meta.authoritativeObservedTsMs;
    if (finite(currentObserved) && observed < currentObserved) return false;

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

  acceptRealtime(
    value: T,
    observedTsMs?: number,
    receivedAtMs: number = Date.now(),
  ): boolean {
    const observed = observedTimestamp(observedTsMs, receivedAtMs);
    const authoritativeObserved = this.state.meta.authoritativeObservedTsMs;
    const currentRealtimeObserved = this.state.meta.realtimeObservedTsMs;
    if (finite(authoritativeObserved) && observed < authoritativeObserved) return false;
    if (finite(currentRealtimeObserved) && observed < currentRealtimeObserved) return false;

    this.state.value = value;
    this.state.meta = {
      ...this.state.meta,
      lastRealtimeAtMs: receivedAtMs,
      lastSuccessAtMs: receivedAtMs,
      realtimeObservedTsMs: observed,
      realtimeVersion: this.state.meta.realtimeVersion + 1,
      lastSource: 'realtime',
      lastError: undefined,
    };
    this.state.freshness = 'fresh';
    return true;
  }

  recordError(error: unknown, receivedAtMs: number = Date.now()): void {
    this.state.meta = {
      ...this.state.meta,
      lastErrorAtMs: receivedAtMs,
      lastError: error instanceof Error ? error.message : String(error),
    };
    this.state.freshness = classifyReconciliationFreshness(receivedAtMs, this.state.meta, this.thresholds);
  }
}
