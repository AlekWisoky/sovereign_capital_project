import type { FamilyReadiness, LaunchBlockedFamilyDetail, LaunchSummary } from '../commandCenter/types';

export function launchStatusLabel(item: FamilyReadiness): string {
  if (item.active) return 'Active';
  if (item.status === 'quarantined') return 'Quarantined';
  if (item.status === 'degraded') return `Degraded · ${item.degradedState || item.currentHealthState || 'restricted'}`;
  if (item.ready) return 'Ready';
  return item.blockers?.[0] || item.reasons?.[0] || 'Not ready';
}

export function launchWhyNow(summary?: LaunchSummary | null): string[] {
  if (!summary) return [];
  if (summary.recommendation?.whyNow?.length) return summary.recommendation.whyNow;
  if (!summary.nextRecommendedFamily) {
    if (summary.recommendation?.holdReasonCodes?.length) return summary.recommendation.holdReasonCodes;
    if (summary.holdReasonCodes?.length) return summary.holdReasonCodes;
    if (summary.recommendation?.recoveryReasonCodes?.length) return summary.recommendation.recoveryReasonCodes;
    if (summary.recoveryReasonCodes?.length) return summary.recoveryReasonCodes;
    if (summary.recommendation?.holdReasonCode) return [summary.recommendation.holdReasonCode];
    if (summary.holdReasonCode) return [summary.holdReasonCode];
    if (summary.recommendation?.recoveryReasonCode && summary.recommendation.recoveryReasonCode !== 'ok') return [summary.recommendation.recoveryReasonCode];
    if (summary.recoveryReasonCode && summary.recoveryReasonCode !== 'ok') return [summary.recoveryReasonCode];
  }
  return summary.reasons ?? [];
}

export function launchRecoveryFreshnessLine(summary?: LaunchSummary | null): string {
  if (!summary) return '';
  const freshnessCodes = summary.recommendation?.recoveryFreshnessReasonCodes?.length
    ? summary.recommendation.recoveryFreshnessReasonCodes
    : summary.recoveryFreshnessReasonCodes?.length
      ? summary.recoveryFreshnessReasonCodes
      : summary.recommendation?.recoveryFreshnessReasonCode && summary.recommendation.recoveryFreshnessReasonCode !== 'ok'
        ? [summary.recommendation.recoveryFreshnessReasonCode]
        : summary.recoveryFreshnessReasonCode && summary.recoveryFreshnessReasonCode !== 'ok'
          ? [summary.recoveryFreshnessReasonCode]
          : [];
  if (!freshnessCodes.length) return '';
  const freshnessClass = String(summary.recommendation?.recoveryFreshnessClass || summary.recoveryFreshnessClass || '');
  const nextAction = String(summary.recommendation?.recoveryFreshnessNextAction || summary.recoveryFreshnessNextAction || '');
  const detail = freshnessCodes.map(humanize).join(' and ');
  return `${detail}${freshnessClass ? ` · class ${humanize(freshnessClass)}` : ''}${nextAction ? ` · next ${humanize(nextAction)}` : ''}`;
}

export function launchRecoveryLine(summary?: LaunchSummary | null): string {
  if (!summary) return '';
  const recoveryCodes = summary.recommendation?.recoveryReasonCodes?.length
    ? summary.recommendation.recoveryReasonCodes
    : summary.recoveryReasonCodes?.length
      ? summary.recoveryReasonCodes
      : summary.recommendation?.recoveryReasonCode && summary.recommendation.recoveryReasonCode !== 'ok'
        ? [summary.recommendation.recoveryReasonCode]
        : summary.recoveryReasonCode && summary.recoveryReasonCode !== 'ok'
          ? [summary.recoveryReasonCode]
          : [];
  if (!recoveryCodes.length) return '';
  const nextAction = summary.recommendation?.recoveryNextAction || summary.recoveryNextAction || summary.recommendation?.suggestedNextAction || summary.suggestedNextAction || '';
  const detail = recoveryCodes.map(humanize).join(' and ');
  return nextAction ? `${detail} · next ${humanize(String(nextAction))}` : detail;
}

export function launchRollbackText(summary?: LaunchSummary | null): string {
  if (!summary) return '';
  return summary.rollbackRecommendation || summary.recommendation?.rollbackRecommendation || '';
}

function humanize(value: string): string {
  return value.replace(/_/g, ' ');
}

function humanizeDurationMs(ms?: number): string {
  const value = Number(ms || 0);
  if (!Number.isFinite(value) || value <= 0) return '';
  const totalMinutes = Math.floor(value / 60000);
  if (totalMinutes < 60) return `${totalMinutes}m`;
  const totalHours = Math.floor(totalMinutes / 60);
  if (totalHours < 48) return `${totalHours}h`;
  const totalDays = Math.floor(totalHours / 24);
  return `${totalDays}d`;
}

function yesNo(value?: boolean): string {
  return value ? 'yes' : 'no';
}

function detailReason(detail: LaunchBlockedFamilyDetail): string {
  const specific = detail.internalPrimeReasonCodes?.[0]
    || detail.capitalTruthReasonCodes?.[0]
    || detail.capitalTruthHealth?.reasonCodes?.[0]
    || detail.blockedBy?.[0]
    || detail.reasonCode;
  return humanize(String(specific || 'not_ready'));
}

export function launchWhyNotLines(summary?: LaunchSummary | null): string[] {
  if (!summary) return [];
  const details = summary.recommendation?.whyNotOthersDetails ?? summary.blockedFamilyDetails ?? {};
  if (Object.keys(details).length) {
    return Object.entries(details).map(([family, detail]) => {
      const nextAction = detail.suggestedNextAction || detail.capitalTruthHealth?.nextAction;
      const next = nextAction ? ` · next ${humanize(String(nextAction))}` : '';
      return `${humanize(family)} = ${detailReason(detail)}${next}`;
    });
  }
  const whyNot = summary.recommendation?.whyNotOthers ?? summary.blockedFamilies ?? {};
  return Object.entries(whyNot).map(([family, reason]) => `${humanize(family)} = ${humanize(String(reason))}`);
}

export function launchWhyNotPreview(summary?: LaunchSummary | null, limit = 3): string[] {
  if (!summary) return [];
  return launchWhyNotLines(summary).slice(0, Math.max(0, limit));
}

export function launchWhyNotOverflowCount(summary?: LaunchSummary | null, limit = 3): number {
  if (!summary) return 0;
  const lines = launchWhyNotLines(summary);
  return Math.max(0, lines.length - Math.max(0, limit));
}

export function familyDependencyRows(item: FamilyReadiness): { label: string; ok: boolean }[] {
  return [
    { label: 'Telemetry', ok: Boolean(item.telemetrySufficient) },
    { label: 'Capital', ok: Boolean(item.capitalReady) },
    { label: 'Internal prime', ok: Boolean(item.internalPrimeReady) },
    { label: 'Stage mandate', ok: Boolean(item.stageAllowed) },
  ];
}

export function launchRecoveryReliabilityLine(summary?: LaunchSummary | null): string {
  if (!summary) return '';
  const cls = String(summary.recommendation?.recoveryReliabilityClass || summary.recoveryReliabilityClass || '');
  const codes = summary.recommendation?.recoveryReliabilityReasonCodes?.length
    ? summary.recommendation.recoveryReliabilityReasonCodes
    : summary.recoveryReliabilityReasonCodes?.length
      ? summary.recoveryReliabilityReasonCodes
      : summary.recommendation?.recoveryReliabilityReasonCode && summary.recommendation.recoveryReliabilityReasonCode !== 'ok'
        ? [summary.recommendation.recoveryReliabilityReasonCode]
        : summary.recoveryReliabilityReasonCode && summary.recoveryReliabilityReasonCode !== 'ok'
          ? [summary.recoveryReliabilityReasonCode]
          : [];
  const recoveredFragile = Boolean(typeof summary.recommendation?.recoveryRecoveredFragile === 'boolean' ? summary.recommendation.recoveryRecoveredFragile : summary.recoveryRecoveredFragile);
  if (!cls || (cls === 'stable' && !recoveredFragile && !codes.length)) return '';
  const next = String(summary.recommendation?.recoveryReliabilityNextAction || summary.recoveryReliabilityNextAction || '');
  const detail = codes.length ? codes.map(humanize).join(' and ') : `class ${humanize(cls)}`;
  return `${detail}${cls ? ` · class ${humanize(cls)}` : ''}${recoveredFragile ? ' · recovered fragile yes' : ''}${next ? ` · next ${humanize(next)}` : ''}`;
}


export function launchRecoveryHistoryLine(summary?: LaunchSummary | null): string {
  if (!summary) return '';
  const status = String(summary.recommendation?.recoveryHistoryStatus || summary.recoveryHistoryStatus || '');
  if (!status || status === 'steady') return '';
  const component = String(summary.recommendation?.recoveryHistoryComponent || summary.recoveryHistoryComponent || '');
  const degradedSinceTsMs = Number(summary.recommendation?.recoveryDegradedSinceTsMs || summary.recoveryDegradedSinceTsMs || 0);
  const recoveredAtTsMs = Number(summary.recommendation?.recoveryRecoveredAtTsMs || summary.recoveryRecoveredAtTsMs || 0);
  const durationMs = Number(summary.recommendation?.recoveryDegradedDurationMs || summary.recoveryDegradedDurationMs || 0);
  const degradedCount = Number(summary.recommendation?.recoveryDegradedCount || summary.recoveryDegradedCount || 0);
  const lastHealthyTsMs = Number(summary.recommendation?.recoveryLastHealthyTsMs || summary.recoveryLastHealthyTsMs || 0);
  const recoveredRecently = Boolean(typeof summary.recommendation?.recoveryRecoveredRecently === 'boolean' ? summary.recommendation?.recoveryRecoveredRecently : summary.recoveryRecoveredRecently);
  const severity = String(summary.recommendation?.recoveryDegradationSeverityClass || summary.recoveryDegradationSeverityClass || '');
  const parts = [humanize(status)];
  if (component) parts.push(`component ${humanize(component)}`);
  const duration = humanizeDurationMs(durationMs);
  if (status === 'degraded' && duration) parts.push(`for ${duration}`);
  if (degradedCount > 0) parts.push(`count ${degradedCount}`);
  if (severity) parts.push(`severity ${humanize(severity)}`);
  if (status === 'recovered' && recoveredAtTsMs > 0) parts.push(`recovered at ${new Date(recoveredAtTsMs).toISOString()}`);
  if (status === 'degraded' && degradedSinceTsMs > 0) parts.push(`since ${new Date(degradedSinceTsMs).toISOString()}`);
  if (lastHealthyTsMs > 0) parts.push(`last healthy ${new Date(lastHealthyTsMs).toISOString()}`);
  if (status === 'recovered') parts.push(`recovered recently ${yesNo(recoveredRecently)}`);
  return parts.join(' · ');
}
