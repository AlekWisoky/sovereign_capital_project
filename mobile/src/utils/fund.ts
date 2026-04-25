import type { FundHealthSummary } from '../commandCenter/types';

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

export function fundHealthHoldReasonCodes(summary?: FundHealthSummary | null): string[] {
  if (!summary) return [];
  if (summary.holdReasonCodes?.length) return summary.holdReasonCodes;
  if (summary.holdReasonCode) return [summary.holdReasonCode];
  if (summary.capitalTruthHealth?.blocked && summary.capitalTruthHealth.reasonCodes?.length) return summary.capitalTruthHealth.reasonCodes;
  return [];
}

export function fundHealthRecoveryFreshnessLine(summary?: FundHealthSummary | null): string {
  if (!summary) return '';
  const codes = summary.recoveryFreshnessReasonCodes?.length
    ? summary.recoveryFreshnessReasonCodes
    : summary.recoveryFreshnessReasonCode && summary.recoveryFreshnessReasonCode !== 'ok'
      ? [summary.recoveryFreshnessReasonCode]
      : [];
  if (!codes.length) return '';
  const freshnessClass = String(summary.recoveryFreshnessClass || '');
  const next = summary.recoveryFreshnessNextAction ? ` · next ${humanize(String(summary.recoveryFreshnessNextAction))}` : '';
  return `${codes.map((value) => humanize(String(value))).join(' · ')}${freshnessClass ? ` · class ${humanize(freshnessClass)}` : ''}${next}`;
}

export function fundHealthHoldLine(summary?: FundHealthSummary | null): string {
  const codes = fundHealthHoldReasonCodes(summary);
  if (!codes.length) return '';
  const nextAction = summary?.suggestedNextAction || summary?.capitalTruthHealth?.nextAction;
  const next = nextAction ? ` · next ${humanize(String(nextAction))}` : '';
  return `${codes.map((value) => humanize(String(value))).join(' · ')}${next}`;
}

export function fundHealthRecoveryReliabilityLine(summary?: FundHealthSummary | null): string {
  if (!summary) return '';
  const cls = String(summary.recoveryReliabilityClass || '');
  const codes = summary.recoveryReliabilityReasonCodes?.length
    ? summary.recoveryReliabilityReasonCodes
    : summary.recoveryReliabilityReasonCode && summary.recoveryReliabilityReasonCode !== 'ok'
      ? [summary.recoveryReliabilityReasonCode]
      : [];
  if (!cls || (cls === 'stable' && !summary.recoveryRecoveredFragile && !codes.length)) return '';
  const next = summary.recoveryReliabilityNextAction ? ` · next ${humanize(String(summary.recoveryReliabilityNextAction))}` : '';
  const fragile = summary.recoveryRecoveredFragile ? ' · recovered fragile yes' : '';
  const detail = codes.length ? `${codes.map((value) => humanize(String(value))).join(' · ')}` : `class ${humanize(cls)}`;
  return `${detail}${cls ? ` · class ${humanize(cls)}` : ''}${fragile}${next}`;
}


export function fundHealthRecoveryHistoryLine(summary?: FundHealthSummary | null): string {
  if (!summary) return '';
  const status = String(summary.recoveryHistoryStatus || '');
  if (!status || status === 'steady') return '';
  const component = String(summary.recoveryHistoryComponent || '');
  const degradedSinceTsMs = Number(summary.recoveryDegradedSinceTsMs || 0);
  const recoveredAtTsMs = Number(summary.recoveryRecoveredAtTsMs || 0);
  const durationMs = Number(summary.recoveryDegradedDurationMs || 0);
  const degradedCount = Number(summary.recoveryDegradedCount || 0);
  const lastHealthyTsMs = Number(summary.recoveryLastHealthyTsMs || 0);
  const recoveredRecently = Boolean(summary.recoveryRecoveredRecently);
  const severity = String(summary.recoveryDegradationSeverityClass || '');
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
