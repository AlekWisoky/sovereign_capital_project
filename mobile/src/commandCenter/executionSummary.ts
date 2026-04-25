import type { CommandCenterSnapshot, ExplainResponse } from './types';

export function endpointRankingRows(snapshot?: CommandCenterSnapshot | null) {
  const lanes = (snapshot?.execution?.endpointQuality?.lanes ?? {}) as Record<string, { endpoints?: Array<any>; relays?: Array<any> }>;
  const rows = Object.entries(lanes).flatMap(([lane, bucket]) => {
    const endpoints = Array.isArray(bucket?.endpoints) ? bucket.endpoints : [];
    const relays = Array.isArray(bucket?.relays) ? bucket.relays : [];
    const ranked = [...endpoints, ...relays].filter((row) => row && (row.endpoint || row.url)).slice(0, 3).map((row) => ({ lane, endpoint: String(row.endpoint ?? row.url ?? ''), score: Number(row.score ?? row.quality ?? 0), avgLatencyMs: Number(row.avg_latency_ms ?? row.avgLatencyMs ?? row.latency_ms_ema ?? 0), successRate: Number(row.success_rate ?? row.successRate ?? 0), relay: relays.includes(row) }));
    return ranked;
  });
  return rows.sort((a, b) => b.score - a.score || a.avgLatencyMs - b.avgLatencyMs).slice(0, 8);
}

export function endpointUniverseRows(snapshot?: CommandCenterSnapshot | null) {
  const buckets = (snapshot?.execution?.endpointUniverse ?? {}) as Record<string, { lane?: string; candidates?: Array<any>; relays?: Array<any>; reason?: string }>;
  return Object.entries(buckets).flatMap(([bucket, value]) => {
    const candidates = [...(Array.isArray(value?.candidates) ? value.candidates : []), ...(Array.isArray(value?.relays) ? value.relays : [])];
    return candidates.slice(0, 4).map((row) => ({ bucket, lane: String(value?.lane ?? bucket).toUpperCase(), endpoint: String(row.url ?? row.endpoint ?? ''), source: String(row.source ?? 'unknown'), privacyClass: String(row.privacy_class ?? 'public'), preferred: Boolean(row.operator_preferred), reason: String(value?.reason ?? '') }));
  });
}

export function routeQualityRows(snapshot?: CommandCenterSnapshot | null) {
  const items = Array.isArray(snapshot?.execution?.routeQuality?.items) ? snapshot!.execution!.routeQuality!.items! : [];
  return items.slice().sort((a, b) => Number(b.quality ?? 0) - Number(a.quality ?? 0)).slice(0, 6).map((item) => ({ label: `${String(item.route_family ?? '').replace(/_/g, ' ')} · ${(Array.isArray(item.venue_subset) ? item.venue_subset.join('+') : '') || 'default'}`, quality: Number(item.quality ?? 0), successRate: Number(item.success_rate ?? 0), meanEdgeUsd: Number(item.mean_realized_edge_usd ?? 0), pair: String(item.pair ?? ''), sizeBucket: String(item.size_bucket ?? ''), latencyClass: String(item.latency_class ?? '') }));
}

export function liveFragilitySummary(snapshot?: CommandCenterSnapshot | null) {
  const rows = Array.isArray(snapshot?.execution?.liveExecution?.items) ? snapshot!.execution!.liveExecution!.items! : [];
  const top = rows.slice().sort((a, b) => Number(b.adversarial?.interferenceProbability ?? 0) - Number(a.adversarial?.interferenceProbability ?? 0))[0];
  if (!top) {
    return { fragility: 0, requiresPrivateLane: false, endpoint: '', routeFamily: '', fallbackReady: false, provider: '', providerChoiceReason: '', killReasons: [] as string[], routeInvalidCauses: [] as string[], pendingCount: 0 };
  }
  return { fragility: Number(top.adversarial?.interferenceProbability ?? 0), requiresPrivateLane: Boolean(top.adversarial?.requiresPrivateLane), endpoint: String(top.endpoint ?? ''), routeFamily: String(top.routeFamily ?? ''), fallbackReady: Boolean(top.fallbackReady), provider: String(top.flashloan?.selectedProvider ?? (top.flashloan?.providerPriority ?? [])[0] ?? top.flashloan?.fallbackProvider ?? ''), providerChoiceReason: String(top.flashloan?.providerChoiceReason ?? top.flashloan?.sizing?.provider_choice_reason ?? ''), killReasons: Array.isArray(top.flashloan?.reasonCodes) ? top.flashloan!.reasonCodes! : [], routeInvalidCauses: Array.isArray(top.routeInvalidCauses) ? top.routeInvalidCauses : [], pendingCount: Number(top.adversarial?.pendingCount ?? 0), borrowMult: Number(top.flashloan?.sizing?.borrow_mult ?? 1), sizeMult: Number(top.flashloan?.sizing?.size_mult ?? 1) };
}

export function killSwitchReasons(snapshot?: CommandCenterSnapshot | null): string[] {
  const suppressions = (snapshot?.execution?.killSwitch?.suppressions ?? {}) as Record<string, any>;
  return Object.entries(suppressions).flatMap(([scope, payload]) => {
    const reasons = Array.isArray(payload?.reason_codes) ? payload.reason_codes : [];
    return reasons.map((reason: string) => `${scope}: ${reason}`);
  }).slice(0, 8);
}

export function formatExplainResponse(explain?: ExplainResponse | null): string {
  if (!explain) return '(no explanation available)';
  const parts: string[] = [];
  if (explain.causal?.whyRoute) parts.push(`Why this route: ${explain.causal.whyRoute}`);
  if (explain.causal?.whySize) parts.push(`Why this size: ${explain.causal.whySize}`);
  if (explain.causal?.whyLane) parts.push(`Why this lane: ${explain.causal.whyLane}`);
  if (explain.causal?.whyNow) parts.push(`Why now: ${explain.causal.whyNow}`);
  const whyNot = Array.isArray(explain.causal?.whyNot) ? explain.causal!.whyNot! : [];
  if (whyNot.length) parts.push(`Why not alternatives: ${whyNot.map((row) => `${row.kind}:${row.candidate} (${row.reason})`).join('; ')}`);
  const invalidCauses = Array.isArray(explain.causal?.routeInvalidCauses) ? explain.causal!.routeInvalidCauses! : [];
  if (invalidCauses.length) parts.push(`Invalidation causes: ${invalidCauses.join(', ')}`);
  const suppressions = Array.isArray(explain.causal?.suppressionReasons) ? explain.causal!.suppressionReasons! : [];
  if (suppressions.length) parts.push(`Suppression reasons: ${suppressions.join(', ')}`);
  const svc = explain.causal?.serviceSummary;
  if (svc) {
    const svcBits = Object.entries(svc)
      .map(([name, row]) => {
        const status = typeof (row as any)?.ok === 'boolean' ? (((row as any).ok === true) ? 'ok' : 'degraded') : (((row as any)?.goalAchieved === true) ? 'achieved' : ((row as any)?.pacing ? String((row as any).pacing) : 'summary'));
        return `${name}:${status}`;
      })
      .join(', ');
    if (svcBits) parts.push(`Service health: ${svcBits}`);
  }
  if (!parts.length && explain.text) parts.push(explain.text);
  return parts.join('\n\n');
}


export function wealthGoalSummary(snapshot?: CommandCenterSnapshot | null) {
  const goal = snapshot?.wealthGoal;
  if (!goal) {
    return { status: 'unconfigured', pacing: '', progressPct: 0, nextGoalAllowed: false, explanation: '' };
  }
  const explanation = typeof goal.explanation?.why_posture === 'string'
    ? String(goal.explanation.why_posture)
    : typeof goal.explanation?.why_next_goal === 'string'
      ? String(goal.explanation.why_next_goal)
      : '';
  return {
    status: String((goal as any).goalStatus ?? (goal.goalAchieved ? 'achieved' : (goal.nextGoalAllowed === false ? 'capped' : 'active'))),
    pacing: String(goal.pacing ?? ''),
    urgency: String((goal as any).goalUrgency ?? ''),
    progressPct: Number(goal.progressPct ?? 0),
    nextGoalAllowed: Boolean(goal.nextGoalAllowed ?? true),
    explanation,
    nextGoalReasons: Array.isArray(goal.nextGoalReasons) ? goal.nextGoalReasons : [],
    nextGoalBlockedReasons: Array.isArray((goal as any).nextGoalBlockedReasons) ? (goal as any).nextGoalBlockedReasons : [],
    goalLadder: Array.isArray((goal as any).goalLadder) ? (goal as any).goalLadder : [],
    capitalBaseUsd: Number((goal as any).capitalBaseUsd ?? 0),
    executionRealismScore: Number((goal as any).executionRealismScore ?? 0),
    stabilityScore: Number((goal as any).stabilityScore ?? 0),
    riskScore: Number((goal as any).riskScore ?? 0),
    nextGoalAggressivenessHint: Number((goal as any).nextGoalAggressivenessHint ?? 0),
    goalVelocityPctPerDay: Number((goal as any).goalVelocityPctPerDay ?? 0),
    requiredVelocityPctPerDay: Number((goal as any).requiredVelocityPctPerDay ?? 0),
    goalHorizonCompatibility: Number((goal as any).goalHorizonCompatibility ?? 1),
    pacingReasons: Array.isArray(goal.pacingReasons) ? goal.pacingReasons : [],
  };
}
