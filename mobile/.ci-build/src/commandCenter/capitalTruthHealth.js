"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.usesCapitalTruthHealthLegacyFallback = exports.capitalTruthHealthLegacyFields = exports.normalizeCapitalTruthHealth = void 0;
function asRecord(value) {
    return value && typeof value === "object" ? value : {};
}
function pickString(value, fallback) {
    if (typeof value === "string")
        return value;
    if (typeof value === "number" && Number.isFinite(value))
        return String(value);
    return fallback;
}
function pickBoolean(value, fallback) {
    return typeof value === "boolean" ? value : fallback;
}
function pickNumber(value, fallback) {
    if (typeof value === "number" && Number.isFinite(value))
        return value;
    return fallback;
}
function pickStringArray(value, fallback) {
    return Array.isArray(value) ? value.map((x) => String(x)) : fallback;
}
function hasFields(value) {
    return Boolean(value) && typeof value === "object" && Object.keys(value).length > 0;
}
function normalizeCapitalTruthHealth(value, fallback = {}) {
    const record = asRecord(value);
    const stateRecord = asRecord(record.stateContract ?? record.state_contract ?? fallback.stateContract);
    const reasonCode = pickString(record.reasonCode ?? record.reason_code, fallback.reasonCode);
    const freshnessReasonCode = pickString(record.freshnessReasonCode ?? record.freshness_reason_code, fallback.freshnessReasonCode);
    const recoveryReasonCode = pickString(record.recoveryReasonCode ?? record.recovery_reason_code, fallback.recoveryReasonCode);
    const reliabilityReasonCode = pickString(record.reliabilityReasonCode ?? record.reliability_reason_code, fallback.reliabilityReasonCode);
    const stateReasonCode = pickString(stateRecord.reasonCode ?? stateRecord.reason_code);
    const stateContract = hasFields(stateRecord)
        ? {
            status: pickString(stateRecord.status),
            blocked: pickBoolean(stateRecord.blocked),
            reasonCode: stateReasonCode,
            reasonCodes: pickStringArray(stateRecord.reasonCodes ?? stateRecord.reason_codes, stateReasonCode && stateReasonCode !== "ok" ? [stateReasonCode] : undefined),
            nextAction: pickString(stateRecord.nextAction ?? stateRecord.next_action),
        }
        : fallback.stateContract;
    const normalized = {
        status: pickString(record.status, fallback.status),
        blocked: pickBoolean(record.blocked, fallback.blocked),
        reasonCode,
        reasonCodes: pickStringArray(record.reasonCodes ?? record.reason_codes, fallback.reasonCodes ?? (reasonCode && reasonCode !== "ok" ? [reasonCode] : undefined)),
        freshnessClass: pickString(record.freshnessClass ?? record.freshness_class, fallback.freshnessClass),
        freshnessReasonCode,
        freshnessReasonCodes: pickStringArray(record.freshnessReasonCodes ?? record.freshness_reason_codes, fallback.freshnessReasonCodes ?? (freshnessReasonCode && freshnessReasonCode !== "ok" ? [freshnessReasonCode] : undefined)),
        nextAction: pickString(record.nextAction ?? record.next_action, fallback.nextAction),
        recoveryReady: pickBoolean(record.recoveryReady ?? record.recovery_ready, fallback.recoveryReady),
        recoveryStatus: pickString(record.recoveryStatus ?? record.recovery_status, fallback.recoveryStatus),
        recoveryReasonCode,
        recoveryReasonCodes: pickStringArray(record.recoveryReasonCodes ?? record.recovery_reason_codes, fallback.recoveryReasonCodes ?? (recoveryReasonCode && recoveryReasonCode !== "ok" ? [recoveryReasonCode] : undefined)),
        recoveryNextAction: pickString(record.recoveryNextAction ?? record.recovery_next_action, fallback.recoveryNextAction),
        recoveryHistoryStatus: pickString(record.recoveryHistoryStatus ?? record.recovery_history_status, fallback.recoveryHistoryStatus),
        reliabilityClass: pickString(record.reliabilityClass ?? record.reliability_class, fallback.reliabilityClass),
        reliabilityReasonCode,
        reliabilityReasonCodes: pickStringArray(record.reliabilityReasonCodes ?? record.reliability_reason_codes, fallback.reliabilityReasonCodes ?? (reliabilityReasonCode && reliabilityReasonCode !== "ok" ? [reliabilityReasonCode] : undefined)),
        recoveredFragile: pickBoolean(record.recoveredFragile ?? record.recovered_fragile, fallback.recoveredFragile),
        observedTsMs: pickNumber(record.observedTsMs ?? record.observed_ts_ms, fallback.observedTsMs) ?? undefined,
        ledgerLastTsMs: pickNumber(record.ledgerLastTsMs ?? record.ledger_last_ts_ms, fallback.ledgerLastTsMs) ?? undefined,
        ageMs: pickNumber(record.ageMs ?? record.age_ms, fallback.ageMs),
        stateContract,
    };
    return hasFields(normalized) ? normalized : undefined;
}
exports.normalizeCapitalTruthHealth = normalizeCapitalTruthHealth;
function capitalTruthHealthLegacyFields(health) {
    if (!health)
        return {};
    return {
        capitalTruthStatus: health.status,
        capitalTruthReasonCodes: health.reasonCodes,
        capitalTruthFreshnessClass: health.freshnessClass,
        capitalTruthFreshnessReasonCode: health.freshnessReasonCode,
        capitalTruthFreshnessReasonCodes: health.freshnessReasonCodes,
        suggestedNextAction: health.nextAction,
        recoveryReady: health.recoveryReady,
        recoveryStatus: health.recoveryStatus,
        recoveryReasonCode: health.recoveryReasonCode,
        recoveryReasonCodes: health.recoveryReasonCodes,
        recoveryNextAction: health.recoveryNextAction,
        capitalTruthRecoveryHistoryStatus: health.recoveryHistoryStatus,
        capitalTruthReliabilityClass: health.reliabilityClass,
        capitalTruthReliabilityReasonCode: health.reliabilityReasonCode,
        capitalTruthReliabilityReasonCodes: health.reliabilityReasonCodes,
        capitalTruthRecoveredFragile: health.recoveredFragile,
        capitalTruthObservedTsMs: health.observedTsMs,
        capitalTruthLedgerLastTsMs: health.ledgerLastTsMs,
        capitalTruthAgeMs: health.ageMs,
    };
}
exports.capitalTruthHealthLegacyFields = capitalTruthHealthLegacyFields;
function usesCapitalTruthHealthLegacyFallback(value) {
    const record = asRecord(value);
    const nested = hasFields(record.capitalTruthHealth) || hasFields(record.capital_truth_health);
    if (nested)
        return false;
    return Boolean(pickString(record.capitalTruthReasonCode ?? record.capital_truth_reason_code)
        || pickString(record.capitalTruthFreshnessClass ?? record.capital_truth_freshness_class)
        || pickString(record.capitalTruthFreshnessReasonCode ?? record.capital_truth_freshness_reason_code)
        || pickString(record.suggestedNextAction ?? record.suggested_next_action)
        || pickString(record.recoveryStatus ?? record.recovery_status)
        || pickString(record.capitalTruthReliabilityClass ?? record.capital_truth_reliability_class)
        || pickString(record.capitalTruthRecoveryHistoryStatus ?? record.capital_truth_recovery_history_status)
        || (pickStringArray(record.capitalTruthReasonCodes ?? record.capital_truth_reason_codes) || []).length
        || (pickStringArray(record.capitalTruthFreshnessReasonCodes ?? record.capital_truth_freshness_reason_codes) || []).length);
}
exports.usesCapitalTruthHealthLegacyFallback = usesCapitalTruthHealthLegacyFallback;
