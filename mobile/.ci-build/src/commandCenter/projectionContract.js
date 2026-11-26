"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.projectionCompatibilityAlert = exports.mergeProjectionCompatibility = exports.evaluateProjectionCompatibility = exports.normalizeSummaryContract = void 0;
const CANONICAL_SUMMARY_CONTRACT_VERSION = "canonical_summary_read_contract_v1";
function asRecord(value) {
    return value && typeof value === "object" ? value : {};
}
function pickString(value) {
    if (typeof value === "string" && value.trim())
        return value;
    return undefined;
}
function normalizeSummaryContract(value) {
    const record = asRecord(value);
    if (!Object.keys(record).length)
        return undefined;
    return {
        ok: typeof record.ok === "boolean" ? record.ok : undefined,
        contractVersion: pickString(record.contractVersion ?? record.contract_version),
        truthFamily: pickString(record.truthFamily ?? record.truth_family),
        readModel: pickString(record.readModel ?? record.read_model),
        synthesized: typeof record.synthesized === "boolean" ? record.synthesized : undefined,
        capitalContractVersion: pickString(record.capitalContractVersion ?? record.capital_contract_version),
        capitalPolicyVersion: pickString(record.capitalPolicyVersion ?? record.capital_policy_version),
        stateContract: asRecord(record.stateContract ?? record.state_contract),
        sourceContracts: asRecord(record.sourceContracts ?? record.source_contracts),
    };
}
exports.normalizeSummaryContract = normalizeSummaryContract;
function evaluateProjectionCompatibility(value, expectation) {
    const summaryContract = normalizeSummaryContract(value);
    const reasonCodes = [];
    if (!summaryContract) {
        reasonCodes.push("summary_contract_missing");
    }
    else {
        if (summaryContract.contractVersion && summaryContract.contractVersion !== CANONICAL_SUMMARY_CONTRACT_VERSION) {
            reasonCodes.push("summary_contract_version_unexpected");
        }
        if (summaryContract.truthFamily !== expectation.truthFamily) {
            reasonCodes.push("summary_contract_truth_family_mismatch");
        }
        if (expectation.readModel && summaryContract.readModel !== expectation.readModel) {
            reasonCodes.push("summary_contract_read_model_mismatch");
        }
    }
    if (expectation.fallbackUsed)
        reasonCodes.push("legacy_projection_fallback_used");
    const degraded = reasonCodes.some((code) => code !== "legacy_projection_fallback_used");
    return {
        status: degraded ? "degraded" : reasonCodes.length ? "warning" : "canonical",
        reasonCodes,
        expectedTruthFamily: expectation.truthFamily,
        expectedReadModel: expectation.readModel,
        observedTruthFamily: summaryContract?.truthFamily,
        observedReadModel: summaryContract?.readModel,
        fallbackUsed: Boolean(expectation.fallbackUsed),
    };
}
exports.evaluateProjectionCompatibility = evaluateProjectionCompatibility;
function mergeProjectionCompatibility(sources) {
    const normalized = Object.fromEntries(Object.entries(sources).filter(([, value]) => Boolean(value)));
    if (!Object.keys(normalized).length)
        return undefined;
    const reasonCodes = Object.entries(normalized).flatMap(([name, value]) => value.reasonCodes.map((code) => `${name}:${code}`));
    const degraded = Object.values(normalized).some((value) => value.status === "degraded");
    const warning = Object.values(normalized).some((value) => value.status === "warning");
    return { status: degraded ? "degraded" : warning ? "warning" : "canonical", reasonCodes, sources: normalized };
}
exports.mergeProjectionCompatibility = mergeProjectionCompatibility;
function projectionCompatibilityAlert(compatibility, timestamp) {
    if (!compatibility || compatibility.status === "canonical")
        return undefined;
    const tsMs = typeof timestamp === "number" ? timestamp : Number(timestamp.tsMs);
    const severity = compatibility.status === "degraded" ? "danger" : "warn";
    const detail = compatibility.reasonCodes.length ? compatibility.reasonCodes.join(" · ") : compatibility.status;
    return { id: `projection-compatibility-${tsMs}`, tsMs, severity, title: "Projection compatibility drift", detail };
}
exports.projectionCompatibilityAlert = projectionCompatibilityAlert;
