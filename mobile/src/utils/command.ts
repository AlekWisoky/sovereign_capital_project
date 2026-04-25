import type { CommandCenterSnapshot } from '../commandCenter/types';

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

function pickSuggestedNextAction(snapshot?: CommandCenterSnapshot | null): string {
  if (!snapshot) return '';
  return String(
    snapshot.suggestedNextAction
      || snapshot.launch?.recommendation?.suggestedNextAction
      || snapshot.launch?.suggestedNextAction
      || snapshot.fundSummary?.suggestedNextAction
      || snapshot.fundSummary?.capitalTruthHealth?.nextAction
      || snapshot.capitalTruthHealth?.nextAction
      || '',
  );
}

function pickRecoveryNextAction(snapshot?: CommandCenterSnapshot | null): string {
  if (!snapshot) return '';
  return String(
    snapshot.recoveryNextAction
      || snapshot.fundSummary?.recoveryNextAction
      || snapshot.suggestedNextAction
      || snapshot.fundSummary?.suggestedNextAction
      || snapshot.fundSummary?.capitalTruthHealth?.nextAction
      || snapshot.capitalTruthHealth?.nextAction
      || '',
  );
}

export function commandCenterHoldReasonCodes(snapshot?: CommandCenterSnapshot | null): string[] {
  if (!snapshot) return [];
  if (snapshot.holdReasonCodes?.length) return snapshot.holdReasonCodes;
  if (snapshot.holdReasonCode) return [snapshot.holdReasonCode];
  if (snapshot.launch?.recommendation?.holdReasonCodes?.length) return snapshot.launch.recommendation.holdReasonCodes;
  if (snapshot.launch?.recommendation?.holdReasonCode) return [snapshot.launch.recommendation.holdReasonCode];
  if (snapshot.launch?.holdReasonCodes?.length) return snapshot.launch.holdReasonCodes;
  if (snapshot.launch?.holdReasonCode) return [snapshot.launch.holdReasonCode];
  if (snapshot.fundSummary?.holdReasonCodes?.length) return snapshot.fundSummary.holdReasonCodes;
  if (snapshot.fundSummary?.holdReasonCode) return [snapshot.fundSummary.holdReasonCode];
  if (snapshot.fundSummary?.capitalTruthHealth?.blocked && snapshot.fundSummary.capitalTruthHealth.reasonCodes?.length) return snapshot.fundSummary.capitalTruthHealth.reasonCodes;
  if (snapshot.capitalTruthHealth?.blocked && snapshot.capitalTruthHealth.reasonCodes?.length) return snapshot.capitalTruthHealth.reasonCodes;
  return [];
}

export function commandCenterHoldLine(snapshot?: CommandCenterSnapshot | null): string {
  const codes = commandCenterHoldReasonCodes(snapshot);
  if (!codes.length) return '';
  const next = pickSuggestedNextAction(snapshot);
  return `${codes.map((value: string) => humanize(String(value))).join(' · ')}${next ? ` · next ${humanize(next)}` : ''}`;
}

export function commandCenterRecoveryReasonCodes(snapshot?: CommandCenterSnapshot | null): string[] {
  if (!snapshot) return [];
  if (snapshot.recoveryReasonCodes?.length) return snapshot.recoveryReasonCodes;
  if (snapshot.recoveryReasonCode && snapshot.recoveryReasonCode !== 'ok') return [snapshot.recoveryReasonCode];
  if (snapshot.fundSummary?.recoveryReasonCodes?.length) return snapshot.fundSummary.recoveryReasonCodes;
  if (snapshot.fundSummary?.recoveryReasonCode && snapshot.fundSummary.recoveryReasonCode !== 'ok') return [snapshot.fundSummary.recoveryReasonCode];
  return [];
}

export function commandCenterRecoveryFreshnessLine(snapshot?: CommandCenterSnapshot | null): string {
  if (!snapshot) return '';
  const freshnessClass = String(
    snapshot.recoveryFreshnessClass
      || snapshot.fundSummary?.recoveryFreshnessClass
      || ''
  );
  const reasonCodes = Array.isArray(snapshot.recoveryFreshnessReasonCodes) && snapshot.recoveryFreshnessReasonCodes.length
    ? snapshot.recoveryFreshnessReasonCodes
    : Array.isArray(snapshot.fundSummary?.recoveryFreshnessReasonCodes) && snapshot.fundSummary.recoveryFreshnessReasonCodes.length
      ? snapshot.fundSummary.recoveryFreshnessReasonCodes
      : (snapshot.recoveryFreshnessReasonCode && snapshot.recoveryFreshnessReasonCode !== 'ok')
        ? [snapshot.recoveryFreshnessReasonCode]
        : (snapshot.fundSummary?.recoveryFreshnessReasonCode && snapshot.fundSummary.recoveryFreshnessReasonCode !== 'ok')
          ? [snapshot.fundSummary.recoveryFreshnessReasonCode]
          : [];
  if (!reasonCodes.length) return '';
  const next = String(
    snapshot.recoveryFreshnessNextAction
      || snapshot.fundSummary?.recoveryFreshnessNextAction
      || ''
  );
  const detail = reasonCodes.map((value) => humanize(String(value))).join(' · ');
  return `${detail}${freshnessClass ? ` · class ${humanize(freshnessClass)}` : ''}${next ? ` · next ${humanize(next)}` : ''}`;
}

export function commandCenterRecoveryLine(snapshot?: CommandCenterSnapshot | null): string {
  const codes = commandCenterRecoveryReasonCodes(snapshot);
  if (!codes.length) return '';
  const next = pickRecoveryNextAction(snapshot);
  return `${codes.map((value) => humanize(String(value))).join(' · ')}${next ? ` · next ${humanize(next)}` : ''}`;
}

export function commandCenterExecutionAdvisoryLine(snapshot?: CommandCenterSnapshot | null): string {
  if (!snapshot) return '';
  const active = typeof snapshot.executionAdvisoryActive === 'boolean'
    ? snapshot.executionAdvisoryActive
    : Boolean(snapshot.executionAdvisoryClass && snapshot.executionAdvisoryClass !== 'stable');
  const cls = String(snapshot.executionAdvisoryClass || snapshot.fundSummary?.recoveryReliabilityClass || '');
  const severity = String(snapshot.executionAdvisorySeverity || (cls === 'stable' ? 'normal' : cls === 'cautious' ? 'caution' : cls ? 'warning' : 'normal'));
  const codes = Array.isArray(snapshot.executionAdvisoryReasonCodes) && snapshot.executionAdvisoryReasonCodes.length
    ? snapshot.executionAdvisoryReasonCodes
    : Array.isArray(snapshot.fundSummary?.recoveryReliabilityReasonCodes) && snapshot.fundSummary.recoveryReliabilityReasonCodes.length
      ? snapshot.fundSummary.recoveryReliabilityReasonCodes
      : (snapshot.executionAdvisoryReasonCode && snapshot.executionAdvisoryReasonCode !== 'ok')
        ? [snapshot.executionAdvisoryReasonCode]
        : (snapshot.fundSummary?.recoveryReliabilityReasonCode && snapshot.fundSummary.recoveryReliabilityReasonCode !== 'ok')
          ? [snapshot.fundSummary.recoveryReliabilityReasonCode]
          : [];
  if (!active && !codes.length && (!cls || cls === 'stable')) return '';
  const next = String(snapshot.executionAdvisoryNextAction || snapshot.fundSummary?.recoveryReliabilityNextAction || '');
  const detail = codes.length ? codes.map((value) => humanize(String(value))).join(' · ') : `class ${humanize(cls)}`;
  return `${detail}${severity ? ` · severity ${humanize(severity)}` : ''}${cls ? ` · class ${humanize(cls)}` : ''}${next ? ` · next ${humanize(next)}` : ''}`;
}

export function commandCenterRecoveryReliabilityLine(snapshot?: CommandCenterSnapshot | null): string {
  if (!snapshot) return '';
  const cls = String(snapshot.recoveryReliabilityClass || snapshot.fundSummary?.recoveryReliabilityClass || '');
  const codes = Array.isArray(snapshot.recoveryReliabilityReasonCodes) && snapshot.recoveryReliabilityReasonCodes.length
    ? snapshot.recoveryReliabilityReasonCodes
    : Array.isArray(snapshot.fundSummary?.recoveryReliabilityReasonCodes) && snapshot.fundSummary.recoveryReliabilityReasonCodes.length
      ? snapshot.fundSummary.recoveryReliabilityReasonCodes
      : (snapshot.recoveryReliabilityReasonCode && snapshot.recoveryReliabilityReasonCode !== 'ok')
        ? [snapshot.recoveryReliabilityReasonCode]
        : (snapshot.fundSummary?.recoveryReliabilityReasonCode && snapshot.fundSummary.recoveryReliabilityReasonCode !== 'ok')
          ? [snapshot.fundSummary.recoveryReliabilityReasonCode]
          : [];
  const recoveredFragile = Boolean(typeof snapshot.recoveryRecoveredFragile === 'boolean' ? snapshot.recoveryRecoveredFragile : snapshot.fundSummary?.recoveryRecoveredFragile);
  if (!cls || (cls === 'stable' && !recoveredFragile && !codes.length)) return '';
  const next = String(snapshot.recoveryReliabilityNextAction || snapshot.fundSummary?.recoveryReliabilityNextAction || '');
  const detail = codes.length ? codes.map((value) => humanize(String(value))).join(' · ') : `class ${humanize(cls)}`;
  return `${detail}${cls ? ` · class ${humanize(cls)}` : ''}${recoveredFragile ? ' · recovered fragile yes' : ''}${next ? ` · next ${humanize(next)}` : ''}`;
}


export function commandCenterRecoveryHistoryLine(snapshot?: CommandCenterSnapshot | null): string {
  if (!snapshot) return '';
  const status = String(snapshot.recoveryHistoryStatus || snapshot.fundSummary?.recoveryHistoryStatus || '');
  if (!status || status === 'steady') return '';
  const component = String(snapshot.recoveryHistoryComponent || snapshot.fundSummary?.recoveryHistoryComponent || '');
  const degradedSinceTsMs = Number(snapshot.recoveryDegradedSinceTsMs || snapshot.fundSummary?.recoveryDegradedSinceTsMs || 0);
  const recoveredAtTsMs = Number(snapshot.recoveryRecoveredAtTsMs || snapshot.fundSummary?.recoveryRecoveredAtTsMs || 0);
  const durationMs = Number(snapshot.recoveryDegradedDurationMs || snapshot.fundSummary?.recoveryDegradedDurationMs || 0);
  const degradedCount = Number(snapshot.recoveryDegradedCount || snapshot.fundSummary?.recoveryDegradedCount || 0);
  const lastHealthyTsMs = Number(snapshot.recoveryLastHealthyTsMs || snapshot.fundSummary?.recoveryLastHealthyTsMs || 0);
  const recoveredRecently = Boolean(typeof snapshot.recoveryRecoveredRecently === 'boolean' ? snapshot.recoveryRecoveredRecently : snapshot.fundSummary?.recoveryRecoveredRecently);
  const severity = String(snapshot.recoveryDegradationSeverityClass || snapshot.fundSummary?.recoveryDegradationSeverityClass || '');
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
