import type { CapitalTruthHealth, CommandCenterSnapshot, ControlPatch, EngineSnapshot, ExplainResponse } from "./types";
import { DEMO_SNAPSHOT } from "./demoSeed";
import { apiGet, apiPost, deployInfo, launchState, fetchWealthGoal } from "../api/client";
import { commandCenterHoldLine, commandCenterHoldReasonCodes } from "../utils/command";
import { capitalTruthHealthLegacyFields, normalizeCapitalTruthHealth, usesCapitalTruthHealthLegacyFallback } from "./capitalTruthHealth";
import { evaluateProjectionCompatibility, mergeProjectionCompatibility, normalizeSummaryContract, projectionCompatibilityAlert } from "./projectionContract";

function withCapitalTruthHealth<T extends Record<string, any>>(base: T, rawHealth: unknown, fallback: Partial<CapitalTruthHealth> = {}): T {
  const capitalTruthHealth = normalizeCapitalTruthHealth(rawHealth, fallback);
  return capitalTruthHealth ? ({ ...base, ...capitalTruthHealthLegacyFields(capitalTruthHealth), capitalTruthHealth } as T) : base;
}

function capitalTruthHealthFallback(detail: Record<string, any>): Partial<CapitalTruthHealth> {
  return {
    reasonCodes: Array.isArray(detail?.capitalTruthReasonCodes) ? detail.capitalTruthReasonCodes.map((x: unknown) => String(x)) : undefined,
    freshnessClass: detail?.capitalTruthFreshnessClass ? String(detail.capitalTruthFreshnessClass) : undefined,
    freshnessReasonCode: detail?.capitalTruthFreshnessReasonCode ? String(detail.capitalTruthFreshnessReasonCode) : undefined,
    freshnessReasonCodes: Array.isArray(detail?.capitalTruthFreshnessReasonCodes) ? detail.capitalTruthFreshnessReasonCodes.map((x: unknown) => String(x)) : undefined,
    nextAction: detail?.suggestedNextAction ? String(detail.suggestedNextAction) : undefined,
    recoveryReady: typeof detail?.recoveryReady === "boolean" ? detail.recoveryReady : undefined,
    recoveryStatus: detail?.recoveryStatus ? String(detail.recoveryStatus) : undefined,
    recoveryReasonCode: detail?.recoveryReasonCode ? String(detail.recoveryReasonCode) : undefined,
    recoveryReasonCodes: Array.isArray(detail?.recoveryReasonCodes) ? detail.recoveryReasonCodes.map((x: unknown) => String(x)) : undefined,
    recoveryNextAction: detail?.recoveryNextAction ? String(detail.recoveryNextAction) : undefined,
    recoveryHistoryStatus: detail?.capitalTruthRecoveryHistoryStatus ? String(detail.capitalTruthRecoveryHistoryStatus) : undefined,
    reliabilityClass: detail?.capitalTruthReliabilityClass ? String(detail.capitalTruthReliabilityClass) : undefined,
    reliabilityReasonCode: detail?.capitalTruthReliabilityReasonCode ? String(detail.capitalTruthReliabilityReasonCode) : undefined,
    reliabilityReasonCodes: Array.isArray(detail?.capitalTruthReliabilityReasonCodes) ? detail.capitalTruthReliabilityReasonCodes.map((x: unknown) => String(x)) : undefined,
    recoveredFragile: typeof detail?.capitalTruthRecoveredFragile === "boolean" ? detail.capitalTruthRecoveredFragile : undefined,
    observedTsMs: typeof detail?.capitalTruthObservedTsMs === "number" ? detail.capitalTruthObservedTsMs : undefined,
    ledgerLastTsMs: typeof detail?.capitalTruthLedgerLastTsMs === "number" ? detail.capitalTruthLedgerLastTsMs : undefined,
    ageMs: typeof detail?.capitalTruthAgeMs === "number" || detail?.capitalTruthAgeMs === null ? detail.capitalTruthAgeMs : undefined,
  };
}


function launchBlockedFamilyDetails(value: unknown) {
  if (!value || typeof value !== "object") return {};
  return Object.fromEntries(
    Object.entries(value as Record<string, any>).map(([family, detail]) => {
      const adapted = {
        reasonCode: String(detail?.reason_code ?? detail?.reasonCode ?? ""),
        blockedBy: Array.isArray(detail?.blocked_by) ? detail.blocked_by.map((x: unknown) => String(x)) : Array.isArray(detail?.blockedBy) ? detail.blockedBy.map((x: unknown) => String(x)) : [],
        suggestedNextAction: detail?.suggested_next_action ? String(detail.suggested_next_action) : detail?.suggestedNextAction ? String(detail.suggestedNextAction) : undefined,
        capitalTruthReasonCodes: Array.isArray(detail?.capital_truth_reason_codes) ? detail.capital_truth_reason_codes.map((x: unknown) => String(x)) : Array.isArray(detail?.capitalTruthReasonCodes) ? detail.capitalTruthReasonCodes.map((x: unknown) => String(x)) : undefined,
        globalExecutionReasonCodes: Array.isArray(detail?.global_execution_reason_codes) ? detail.global_execution_reason_codes.map((x: unknown) => String(x)) : Array.isArray(detail?.globalExecutionReasonCodes) ? detail.globalExecutionReasonCodes.map((x: unknown) => String(x)) : undefined,
        internalPrimeReasonCodes: Array.isArray(detail?.internal_prime_reason_codes) ? detail.internal_prime_reason_codes.map((x: unknown) => String(x)) : Array.isArray(detail?.internalPrimeReasonCodes) ? detail.internalPrimeReasonCodes.map((x: unknown) => String(x)) : undefined,
        recoveryReady: typeof detail?.recovery_ready === "boolean" ? detail.recovery_ready : typeof detail?.recoveryReady === "boolean" ? detail.recoveryReady : undefined,
        recoveryStatus: detail?.recovery_status ? String(detail.recovery_status) : detail?.recoveryStatus ? String(detail.recoveryStatus) : undefined,
        recoveryReasonCode: detail?.recovery_reason_code ? String(detail.recovery_reason_code) : detail?.recoveryReasonCode ? String(detail.recoveryReasonCode) : undefined,
        recoveryReasonCodes: Array.isArray(detail?.recovery_reason_codes) ? detail.recovery_reason_codes.map((x: unknown) => String(x)) : Array.isArray(detail?.recoveryReasonCodes) ? detail.recoveryReasonCodes.map((x: unknown) => String(x)) : undefined,
        recoveryNextAction: detail?.recovery_next_action ? String(detail.recovery_next_action) : detail?.recoveryNextAction ? String(detail.recoveryNextAction) : undefined,
        recoveryFreshnessClass: detail?.recovery_freshness_class ? String(detail.recovery_freshness_class) : detail?.recoveryFreshnessClass ? String(detail.recoveryFreshnessClass) : undefined,
        recoveryFreshnessReasonCode: detail?.recovery_freshness_reason_code ? String(detail.recovery_freshness_reason_code) : detail?.recoveryFreshnessReasonCode ? String(detail.recoveryFreshnessReasonCode) : undefined,
        recoveryFreshnessReasonCodes: Array.isArray(detail?.recovery_freshness_reason_codes) ? detail.recovery_freshness_reason_codes.map((x: unknown) => String(x)) : Array.isArray(detail?.recoveryFreshnessReasonCodes) ? detail.recoveryFreshnessReasonCodes.map((x: unknown) => String(x)) : undefined,
        recoveryFreshnessNextAction: detail?.recovery_freshness_next_action ? String(detail.recovery_freshness_next_action) : detail?.recoveryFreshnessNextAction ? String(detail.recoveryFreshnessNextAction) : undefined,
        recoveryHistoryComponent: detail?.recovery_history_component ? String(detail.recovery_history_component) : detail?.recoveryHistoryComponent ? String(detail.recoveryHistoryComponent) : undefined,
        recoveryHistoryStatus: detail?.recovery_history_status ? String(detail.recovery_history_status) : detail?.recoveryHistoryStatus ? String(detail.recoveryHistoryStatus) : undefined,
        recoveryDegradedSinceTsMs: detail?.recovery_degraded_since_ts_ms ? Number(detail.recovery_degraded_since_ts_ms) : detail?.recoveryDegradedSinceTsMs ? Number(detail.recoveryDegradedSinceTsMs) : undefined,
        recoveryRecoveredAtTsMs: detail?.recovery_recovered_at_ts_ms ? Number(detail.recovery_recovered_at_ts_ms) : detail?.recoveryRecoveredAtTsMs ? Number(detail.recoveryRecoveredAtTsMs) : undefined,
        recoveryDegradedDurationMs: detail?.recovery_degraded_duration_ms ? Number(detail.recovery_degraded_duration_ms) : detail?.recoveryDegradedDurationMs ? Number(detail.recoveryDegradedDurationMs) : undefined,
        recoveryDegradedCount: detail?.recovery_degraded_count ? Number(detail.recovery_degraded_count) : detail?.recoveryDegradedCount ? Number(detail.recoveryDegradedCount) : undefined,
        recoveryLastHealthyTsMs: detail?.recovery_last_healthy_ts_ms ? Number(detail.recovery_last_healthy_ts_ms) : detail?.recoveryLastHealthyTsMs ? Number(detail.recoveryLastHealthyTsMs) : undefined,
        recoveryRecoveredRecently: typeof detail?.recovery_recovered_recently === "boolean" ? detail.recovery_recovered_recently : typeof detail?.recoveryRecoveredRecently === "boolean" ? detail.recoveryRecoveredRecently : undefined,
        recoveryDegradationSeverityClass: detail?.recovery_degradation_severity_class ? String(detail.recovery_degradation_severity_class) : detail?.recoveryDegradationSeverityClass ? String(detail.recoveryDegradationSeverityClass) : undefined,
        capitalTruthReliabilityClass: detail?.capital_truth_reliability_class ? String(detail.capital_truth_reliability_class) : detail?.capitalTruthReliabilityClass ? String(detail.capitalTruthReliabilityClass) : undefined,
        capitalTruthReliabilityReasonCode: detail?.capital_truth_reliability_reason_code ? String(detail.capital_truth_reliability_reason_code) : detail?.capitalTruthReliabilityReasonCode ? String(detail.capitalTruthReliabilityReasonCode) : undefined,
        capitalTruthReliabilityReasonCodes: Array.isArray(detail?.capital_truth_reliability_reason_codes) ? detail.capital_truth_reliability_reason_codes.map((x: unknown) => String(x)) : Array.isArray(detail?.capitalTruthReliabilityReasonCodes) ? detail.capitalTruthReliabilityReasonCodes.map((x: unknown) => String(x)) : undefined,
        capitalTruthRecoveredFragile: typeof detail?.capital_truth_recovered_fragile === "boolean" ? detail.capital_truth_recovered_fragile : typeof detail?.capitalTruthRecoveredFragile === "boolean" ? detail.capitalTruthRecoveredFragile : undefined,
        internalPrimeReliabilityClass: detail?.internal_prime_reliability_class ? String(detail.internal_prime_reliability_class) : detail?.internalPrimeReliabilityClass ? String(detail.internalPrimeReliabilityClass) : undefined,
        internalPrimeReliabilityReasonCode: detail?.internal_prime_reliability_reason_code ? String(detail.internal_prime_reliability_reason_code) : detail?.internalPrimeReliabilityReasonCode ? String(detail.internalPrimeReliabilityReasonCode) : undefined,
        internalPrimeReliabilityReasonCodes: Array.isArray(detail?.internal_prime_reliability_reason_codes) ? detail.internal_prime_reliability_reason_codes.map((x: unknown) => String(x)) : Array.isArray(detail?.internalPrimeReliabilityReasonCodes) ? detail.internalPrimeReliabilityReasonCodes.map((x: unknown) => String(x)) : undefined,
        internalPrimeRecoveredFragile: typeof detail?.internal_prime_recovered_fragile === "boolean" ? detail.internal_prime_recovered_fragile : typeof detail?.internalPrimeRecoveredFragile === "boolean" ? detail.internalPrimeRecoveredFragile : undefined,
        recoveryReliabilityClass: detail?.recovery_reliability_class ? String(detail.recovery_reliability_class) : detail?.recoveryReliabilityClass ? String(detail.recoveryReliabilityClass) : undefined,
        recoveryReliabilityReasonCode: detail?.recovery_reliability_reason_code ? String(detail.recovery_reliability_reason_code) : detail?.recoveryReliabilityReasonCode ? String(detail.recoveryReliabilityReasonCode) : undefined,
        recoveryReliabilityReasonCodes: Array.isArray(detail?.recovery_reliability_reason_codes) ? detail.recovery_reliability_reason_codes.map((x: unknown) => String(x)) : Array.isArray(detail?.recoveryReliabilityReasonCodes) ? detail.recoveryReliabilityReasonCodes.map((x: unknown) => String(x)) : undefined,
        recoveryReliabilityNextAction: detail?.recovery_reliability_next_action ? String(detail.recovery_reliability_next_action) : detail?.recoveryReliabilityNextAction ? String(detail.recoveryReliabilityNextAction) : undefined,
        recoveryRecoveredFragile: typeof detail?.recovery_recovered_fragile === "boolean" ? detail.recovery_recovered_fragile : typeof detail?.recoveryRecoveredFragile === "boolean" ? detail.recoveryRecoveredFragile : undefined,
        status: detail?.status ? String(detail.status) : undefined,
        degradedState: detail?.degraded_state ? String(detail.degraded_state) : detail?.degradedState ? String(detail.degradedState) : undefined,
      };
      return [family, withCapitalTruthHealth(adapted, detail?.capital_truth_health ?? detail?.capitalTruthHealth, capitalTruthHealthFallback(adapted))];
    }),
  );
}

export type CommandCenterProvider = {
  snapshot: () => Promise<CommandCenterSnapshot>;
  setControls: (patch: ControlPatch, reason: string) => Promise<{ ok: boolean; error?: string }>;
  explain: () => Promise<ExplainResponse>;
  auditTail: (limit: number) => Promise<{ ok: boolean; items: unknown[] }>;
};

export function createMockCommandCenterProvider(): CommandCenterProvider {
  return {
    snapshot: async () => ({ ...DEMO_SNAPSHOT, dataSource: "mock", liveMode: "demo", sourceLabel: "Demo Seed" }),
    setControls: async () => ({ ok: true }),
    explain: async () => ({ ok: true, text: "Demo mode: connect backend to explain live capital.", facts: {} }),
    auditTail: async () => ({ ok: true, items: [] }),
  };
}

export function createBackendCommandCenterProvider(baseUrl: string, adminKey?: string): CommandCenterProvider {
  const headers = adminKey ? { "X-Admin-Key": adminKey } : undefined;
  return {
    snapshot: async () => {
      let deploy: any = {};
      try {
        deploy = (await deployInfo(baseUrl, adminKey)) as any;
      } catch {
        deploy = {};
      }
      try {
        const snap = (await apiGet(baseUrl, "/api/commandcenter/snapshot", headers)) as CommandCenterSnapshot;
        let engines: EngineSnapshot[] = [];
        let fundSummary: any = undefined;
        let launch: any = undefined;
        let profitMix: any = undefined;
        let execution: any = undefined;
        let services: any = undefined;
        try {
          const engineState = (await apiGet(baseUrl, "/api/engines/state", headers)) as any;
          engines = ((engineState?.summary?.engines ?? []) as any[]).map((row) => ({
            engineId: String(row.engine_type ?? row.engineId ?? "engine"),
            title: String(row.engine_type ?? row.title ?? "Engine").replace(/_/g, " "),
            mode: String(row.mode ?? "observe_only"),
            lifecycle: String(row.lifecycle ?? row.stage ?? row.mode ?? "observe_only"),
            opportunities: Number(row.opportunity_count ?? row.opportunities ?? 0),
            admitted: Number(row.admitted_count ?? row.admitted ?? 0),
            blocked: Number(row.blocked_count ?? row.blocked ?? 0),
            capitalCapPct: Number(row.capital_cap_pct ?? row.capitalCapPct ?? 0),
            confidenceFloor: Number(row.required_confidence ?? row.confidenceFloor ?? 0),
            reason: row.reason ? String(row.reason) : undefined,
          }));
        } catch {
          engines = [];
        }
        try {
          const fund = (await apiGet(baseUrl, '/api/fund/summary', headers)) as any;
          const fundHealth = (fund?.health ?? {}) as Record<string, unknown>;
          const fundSummaryContract = normalizeSummaryContract(fund?.summaryContract ?? fund?.summary_contract);
          const fundProjectionCompatibility = evaluateProjectionCompatibility(
            fund?.summaryContract ?? fund?.summary_contract,
            {
              truthFamily: 'fund',
              readModel: 'fund_summary_projection_v1',
              fallbackUsed: usesCapitalTruthHealthLegacyFallback(fundHealth),
            },
          );
          fundSummary = fund?.health ? withCapitalTruthHealth({
            ...(fundHealth as Record<string, unknown>),
            summaryContract: fundSummaryContract,
            projectionCompatibility: fundProjectionCompatibility,
          }, fund.health?.capitalTruthHealth ?? fund.health?.capital_truth_health, capitalTruthHealthFallback(fundHealth)) : undefined;
          profitMix = fund?.profitMix ? fund.profitMix : undefined;
        } catch {
          fundSummary = undefined;
          profitMix = undefined;
        }
        try {
          const launchStateResp = (await launchState(baseUrl, adminKey)) as any;
          const launchSummaryContract = normalizeSummaryContract(launchStateResp?.summaryContract ?? launchStateResp?.summary_contract);
          const launchProjectionCompatibility = evaluateProjectionCompatibility(
            launchStateResp?.summaryContract ?? launchStateResp?.summary_contract,
            {
              truthFamily: 'launch',
              readModel: 'launch_summary_projection_v1',
              fallbackUsed: usesCapitalTruthHealthLegacyFallback(launchStateResp),
            },
          );
          const blockedFamilyDetails = launchBlockedFamilyDetails(launchStateResp?.blocked_family_details);
          const whyNotOthersDetails = launchBlockedFamilyDetails(launchStateResp?.recommended_plan?.why_not_others_details);
          launch = launchStateResp?.ok ? withCapitalTruthHealth({
            summaryContract: launchSummaryContract,
            projectionCompatibility: launchProjectionCompatibility,
            currentLaunchMode: String((launchStateResp?.profile?.mode ?? 'V1_ONLY')),
            activeFamilies: Array.isArray(launchStateResp?.profile?.active_families) ? launchStateResp.profile.active_families : [],
            nextRecommendedFamily: String(launchStateResp?.recommended_next_family ?? ''),
            blockedFamilies: typeof launchStateResp?.blocked_families === 'object' && launchStateResp?.blocked_families ? launchStateResp.blocked_families : {},
            blockedFamilyDetails,
            families: Array.isArray(launchStateResp?.families) ? launchStateResp.families : [],
            reasons: Array.isArray(launchStateResp?.reasons) ? launchStateResp.reasons : [],
            recommendation: launchStateResp?.recommended_plan ? withCapitalTruthHealth({
              nextFamily: String(launchStateResp.recommended_plan.next_family ?? ''),
              whyNow: Array.isArray(launchStateResp.recommended_plan.why_now) ? launchStateResp.recommended_plan.why_now : [],
              whyNotOthers: typeof launchStateResp.recommended_plan.why_not_others === 'object' && launchStateResp.recommended_plan.why_not_others ? launchStateResp.recommended_plan.why_not_others : {},
              whyNotOthersDetails,
              rollbackRecommendation: String(launchStateResp.recommended_plan.rollback_recommendation ?? ''),
              globalExecutionBlocked: Boolean(launchStateResp.recommended_plan.global_execution_blocked),
              globalExecutionReasonCodes: Array.isArray(launchStateResp.recommended_plan.global_execution_reason_codes) ? launchStateResp.recommended_plan.global_execution_reason_codes.map((x: unknown) => String(x)) : [],
              capitalTruthReasonCodes: Array.isArray(launchStateResp.recommended_plan.capital_truth_reason_codes) ? launchStateResp.recommended_plan.capital_truth_reason_codes.map((x: unknown) => String(x)) : [],
              internalPrimeReasonCodes: Array.isArray(launchStateResp.recommended_plan.internal_prime_reason_codes) ? launchStateResp.recommended_plan.internal_prime_reason_codes.map((x: unknown) => String(x)) : [],
              holdReasonCode: String(launchStateResp.recommended_plan.hold_reason_code ?? ''),
              holdReasonCodes: Array.isArray(launchStateResp.recommended_plan.hold_reason_codes) ? launchStateResp.recommended_plan.hold_reason_codes.map((x: unknown) => String(x)) : [],
              suggestedNextAction: String(launchStateResp.recommended_plan.suggested_next_action ?? ''),
              recoveryReady: typeof launchStateResp.recommended_plan.recovery_ready === 'boolean' ? launchStateResp.recommended_plan.recovery_ready : undefined,
              recoveryStatus: String(launchStateResp.recommended_plan.recovery_status ?? ''),
              recoveryReasonCode: String(launchStateResp.recommended_plan.recovery_reason_code ?? ''),
              recoveryReasonCodes: Array.isArray(launchStateResp.recommended_plan.recovery_reason_codes) ? launchStateResp.recommended_plan.recovery_reason_codes.map((x: unknown) => String(x)) : [],
              recoveryNextAction: String(launchStateResp.recommended_plan.recovery_next_action ?? ''),
              recoveryFreshnessClass: String(launchStateResp.recommended_plan.recovery_freshness_class ?? ''),
              recoveryFreshnessReasonCode: String(launchStateResp.recommended_plan.recovery_freshness_reason_code ?? 'ok'),
              recoveryFreshnessReasonCodes: Array.isArray(launchStateResp.recommended_plan.recovery_freshness_reason_codes) ? launchStateResp.recommended_plan.recovery_freshness_reason_codes.map((x: unknown) => String(x)) : [],
              recoveryFreshnessNextAction: String(launchStateResp.recommended_plan.recovery_freshness_next_action ?? ''),
              recoveryHistoryComponent: String(launchStateResp.recommended_plan.recovery_history_component ?? ''),
              recoveryHistoryStatus: String(launchStateResp.recommended_plan.recovery_history_status ?? 'steady'),
              recoveryDegradedSinceTsMs: Number(launchStateResp.recommended_plan.recovery_degraded_since_ts_ms ?? 0),
              recoveryRecoveredAtTsMs: Number(launchStateResp.recommended_plan.recovery_recovered_at_ts_ms ?? 0),
              recoveryDegradedDurationMs: Number(launchStateResp.recommended_plan.recovery_degraded_duration_ms ?? 0),
              recoveryDegradedCount: Number(launchStateResp.recommended_plan.recovery_degraded_count ?? 0),
              recoveryLastHealthyTsMs: Number(launchStateResp.recommended_plan.recovery_last_healthy_ts_ms ?? 0),
              recoveryRecoveredRecently: Boolean(launchStateResp.recommended_plan.recovery_recovered_recently),
              recoveryDegradationSeverityClass: String(launchStateResp.recommended_plan.recovery_degradation_severity_class ?? ''),
              capitalTruthReliabilityClass: String(launchStateResp.recommended_plan.capital_truth_reliability_class ?? ''),
              capitalTruthReliabilityReasonCode: String(launchStateResp.recommended_plan.capital_truth_reliability_reason_code ?? 'ok'),
              capitalTruthReliabilityReasonCodes: Array.isArray(launchStateResp.recommended_plan.capital_truth_reliability_reason_codes) ? launchStateResp.recommended_plan.capital_truth_reliability_reason_codes.map((x: unknown) => String(x)) : [],
              capitalTruthRecoveredFragile: Boolean(launchStateResp.recommended_plan.capital_truth_recovered_fragile),
              internalPrimeReliabilityClass: String(launchStateResp.recommended_plan.internal_prime_reliability_class ?? ''),
              internalPrimeReliabilityReasonCode: String(launchStateResp.recommended_plan.internal_prime_reliability_reason_code ?? 'ok'),
              internalPrimeReliabilityReasonCodes: Array.isArray(launchStateResp.recommended_plan.internal_prime_reliability_reason_codes) ? launchStateResp.recommended_plan.internal_prime_reliability_reason_codes.map((x: unknown) => String(x)) : [],
              internalPrimeRecoveredFragile: Boolean(launchStateResp.recommended_plan.internal_prime_recovered_fragile),
              recoveryReliabilityClass: String(launchStateResp.recommended_plan.recovery_reliability_class ?? ''),
              recoveryReliabilityReasonCode: String(launchStateResp.recommended_plan.recovery_reliability_reason_code ?? 'ok'),
              recoveryReliabilityReasonCodes: Array.isArray(launchStateResp.recommended_plan.recovery_reliability_reason_codes) ? launchStateResp.recommended_plan.recovery_reliability_reason_codes.map((x: unknown) => String(x)) : [],
              recoveryReliabilityNextAction: String(launchStateResp.recommended_plan.recovery_reliability_next_action ?? ''),
              recoveryRecoveredFragile: Boolean(launchStateResp.recommended_plan.recovery_recovered_fragile),
            }, launchStateResp?.recommended_plan?.capitalTruthHealth ?? launchStateResp?.recommended_plan?.capital_truth_health, capitalTruthHealthFallback(launchStateResp?.recommended_plan ?? {})) : undefined,
            rollbackRecommendation: String(launchStateResp?.recommended_plan?.rollback_recommendation ?? ''),
            healthGraph: typeof launchStateResp?.health_graph === 'object' && launchStateResp?.health_graph ? launchStateResp.health_graph : undefined,
            globalExecutionBlocked: Boolean(launchStateResp?.global_execution_blocked),
            globalExecutionReasonCodes: Array.isArray(launchStateResp?.global_execution_reason_codes) ? launchStateResp.global_execution_reason_codes.map((x: unknown) => String(x)) : [],
            capitalTruthReasonCodes: Array.isArray(launchStateResp?.capital_truth_reason_codes) ? launchStateResp.capital_truth_reason_codes.map((x: unknown) => String(x)) : [],
            internalPrimeReasonCodes: Array.isArray(launchStateResp?.internal_prime_reason_codes) ? launchStateResp.internal_prime_reason_codes.map((x: unknown) => String(x)) : [],
            holdReasonCode: String(launchStateResp?.hold_reason_code ?? ''),
            holdReasonCodes: Array.isArray(launchStateResp?.hold_reason_codes) ? launchStateResp.hold_reason_codes.map((x: unknown) => String(x)) : [],
            suggestedNextAction: String(launchStateResp?.suggested_next_action ?? ''),
            recoveryReady: typeof launchStateResp?.recovery_ready === 'boolean' ? launchStateResp.recovery_ready : undefined,
            recoveryStatus: String(launchStateResp?.recovery_status ?? ''),
            recoveryReasonCode: String(launchStateResp?.recovery_reason_code ?? ''),
            recoveryReasonCodes: Array.isArray(launchStateResp?.recovery_reason_codes) ? launchStateResp.recovery_reason_codes.map((x: unknown) => String(x)) : [],
            recoveryNextAction: String(launchStateResp?.recovery_next_action ?? ''),
            recoveryFreshnessClass: String(launchStateResp?.recovery_freshness_class ?? ''),
            recoveryFreshnessReasonCode: String(launchStateResp?.recovery_freshness_reason_code ?? 'ok'),
            recoveryFreshnessReasonCodes: Array.isArray(launchStateResp?.recovery_freshness_reason_codes) ? launchStateResp.recovery_freshness_reason_codes.map((x: unknown) => String(x)) : [],
            recoveryFreshnessNextAction: String(launchStateResp?.recovery_freshness_next_action ?? ''),
            recoveryHistoryComponent: String(launchStateResp?.recovery_history_component ?? ''),
            recoveryHistoryStatus: String(launchStateResp?.recovery_history_status ?? 'steady'),
            recoveryDegradedSinceTsMs: Number(launchStateResp?.recovery_degraded_since_ts_ms ?? 0),
            recoveryRecoveredAtTsMs: Number(launchStateResp?.recovery_recovered_at_ts_ms ?? 0),
            recoveryDegradedDurationMs: Number(launchStateResp?.recovery_degraded_duration_ms ?? 0),
            recoveryDegradedCount: Number(launchStateResp?.recovery_degraded_count ?? 0),
            recoveryLastHealthyTsMs: Number(launchStateResp?.recovery_last_healthy_ts_ms ?? 0),
            recoveryRecoveredRecently: Boolean(launchStateResp?.recovery_recovered_recently),
            recoveryDegradationSeverityClass: String(launchStateResp?.recovery_degradation_severity_class ?? ''),
            capitalTruthReliabilityClass: String(launchStateResp?.capital_truth_reliability_class ?? ''),
            capitalTruthReliabilityReasonCode: String(launchStateResp?.capital_truth_reliability_reason_code ?? 'ok'),
            capitalTruthReliabilityReasonCodes: Array.isArray(launchStateResp?.capital_truth_reliability_reason_codes) ? launchStateResp.capital_truth_reliability_reason_codes.map((x: unknown) => String(x)) : [],
            capitalTruthRecoveredFragile: Boolean(launchStateResp?.capital_truth_recovered_fragile),
            internalPrimeReliabilityClass: String(launchStateResp?.internal_prime_reliability_class ?? ''),
            internalPrimeReliabilityReasonCode: String(launchStateResp?.internal_prime_reliability_reason_code ?? 'ok'),
            internalPrimeReliabilityReasonCodes: Array.isArray(launchStateResp?.internal_prime_reliability_reason_codes) ? launchStateResp.internal_prime_reliability_reason_codes.map((x: unknown) => String(x)) : [],
            internalPrimeRecoveredFragile: Boolean(launchStateResp?.internal_prime_recovered_fragile),
            recoveryReliabilityClass: String(launchStateResp?.recovery_reliability_class ?? ''),
            recoveryReliabilityReasonCode: String(launchStateResp?.recovery_reliability_reason_code ?? 'ok'),
            recoveryReliabilityReasonCodes: Array.isArray(launchStateResp?.recovery_reliability_reason_codes) ? launchStateResp.recovery_reliability_reason_codes.map((x: unknown) => String(x)) : [],
            recoveryReliabilityNextAction: String(launchStateResp?.recovery_reliability_next_action ?? ''),
            recoveryRecoveredFragile: Boolean(launchStateResp?.recovery_recovered_fragile),
          }, launchStateResp?.capitalTruthHealth ?? launchStateResp?.capital_truth_health, capitalTruthHealthFallback(launchStateResp ?? {})) : undefined;
        } catch {
          launch = undefined;
        }
        try {
          const eq = (await apiGet(baseUrl, '/api/system/execution/quality', headers)) as any;
          const riskLive = (await apiGet(baseUrl, '/api/risk/live-state', headers)) as any;
          services = (await apiGet(baseUrl, '/api/system/services', headers)) as any;
          execution = {
            endpointQuality: eq?.endpoint_quality ?? {},
            endpointUniverse: eq?.endpoint_universe ?? riskLive?.endpoint_universe ?? {},
            routeQuality: eq?.route_quality ?? riskLive?.route_quality ?? {},
            liveExecution: eq?.live_execution ?? riskLive?.live_execution ?? {},
            venueScorecards: eq?.venue_scorecards ?? {},
            drawdown: riskLive?.drawdown ?? eq?.drawdown ?? {},
            killSwitch: riskLive?.kill_switch ?? eq?.kill_switch ?? {},
          };
        } catch {
          execution = undefined;
        }
        let wealthGoal = snap.wealthGoal;
        try {
          if (!wealthGoal || !wealthGoal.explanation) {
            const wg = (await fetchWealthGoal(baseUrl, adminKey)) as any;
            if (wg?.ok && wg?.state) {
              wealthGoal = wg.state;
              wealthGoal.explanation = wg.explanation;
              wealthGoal.history = wg.history;
            }
          }
        } catch {
          // keep snapshot-provided goal
        }
        const snapshotSummaryContract = normalizeSummaryContract((snap as any)?.summaryContract ?? (snap as any)?.summary_contract);
        const snapshotProjectionCompatibility = evaluateProjectionCompatibility(
          (snap as any)?.summaryContract ?? (snap as any)?.summary_contract,
          {
            truthFamily: 'command_center',
            readModel: 'command_center_summary_projection_v1',
            fallbackUsed: usesCapitalTruthHealthLegacyFallback(snap as any),
          },
        );
        const mergedProjectionCompatibility = mergeProjectionCompatibility({
          commandCenter: snapshotProjectionCompatibility,
          fundSummary: fundSummary?.projectionCompatibility,
          launch: launch?.projectionCompatibility,
        });
        const projectionAlert = projectionCompatibilityAlert(mergedProjectionCompatibility, { tsMs: Date.now() });
        const mergedBase = withCapitalTruthHealth({
          ...snap,
          summaryContract: snapshotSummaryContract,
          projectionCompatibility: mergedProjectionCompatibility,
          wealthGoal,
          dataSource: "backend",
          liveMode: engines.length || snap.dataSource === "backend" ? "live" : "backend-mock",
          sourceLabel: String((deploy as any)?.brand?.name || "x∆v"),
          engines,
          fundSummary,
          launch,
          profitMix,
          execution,
          services,
          alerts: projectionAlert ? [projectionAlert, ...((snap as any)?.alerts ?? [])] : (snap as any)?.alerts,
        } as CommandCenterSnapshot, (snap as any)?.capitalTruthHealth ?? (snap as any)?.capital_truth_health ?? fundSummary?.capitalTruthHealth ?? launch?.capitalTruthHealth, capitalTruthHealthFallback({ ...(snap as any), ...(fundSummary as any) }));
        const holdReasonCodes = commandCenterHoldReasonCodes(mergedBase);
        const holdReasonCode = mergedBase.holdReasonCode || holdReasonCodes[0] || '';
        const suggestedNextAction = String(
          mergedBase.suggestedNextAction
          || mergedBase.launch?.recommendation?.suggestedNextAction
          || mergedBase.launch?.suggestedNextAction
          || mergedBase.fundSummary?.suggestedNextAction
          || ''
        );
        const recoveryReasonCodes = Array.isArray(mergedBase.recoveryReasonCodes) && mergedBase.recoveryReasonCodes.length
          ? mergedBase.recoveryReasonCodes
          : Array.isArray(mergedBase.fundSummary?.recoveryReasonCodes) && mergedBase.fundSummary.recoveryReasonCodes.length
            ? mergedBase.fundSummary.recoveryReasonCodes
            : (mergedBase.recoveryReasonCode && mergedBase.recoveryReasonCode !== 'ok')
              ? [mergedBase.recoveryReasonCode]
              : (mergedBase.fundSummary?.recoveryReasonCode && mergedBase.fundSummary.recoveryReasonCode !== 'ok')
                ? [mergedBase.fundSummary.recoveryReasonCode]
                : [];
        const recoveryReasonCode = String(
          mergedBase.recoveryReasonCode
          || recoveryReasonCodes[0]
          || mergedBase.fundSummary?.recoveryReasonCode
          || 'ok'
        );
        const recoveryStatus = String(
          mergedBase.recoveryStatus
          || mergedBase.fundSummary?.recoveryStatus
          || (recoveryReasonCodes.length ? 'degraded' : 'ready')
        );
        const recoveryNextAction = String(
          mergedBase.recoveryNextAction
          || mergedBase.fundSummary?.recoveryNextAction
          || suggestedNextAction
          || ''
        );
        const recoveryFreshnessReasonCodes = Array.isArray((mergedBase as any).recoveryFreshnessReasonCodes) && (mergedBase as any).recoveryFreshnessReasonCodes.length
          ? (mergedBase as any).recoveryFreshnessReasonCodes
          : Array.isArray((mergedBase.fundSummary as any)?.recoveryFreshnessReasonCodes) && (mergedBase.fundSummary as any).recoveryFreshnessReasonCodes.length
            ? (mergedBase.fundSummary as any).recoveryFreshnessReasonCodes
            : ((mergedBase as any).recoveryFreshnessReasonCode && (mergedBase as any).recoveryFreshnessReasonCode !== 'ok')
              ? [String((mergedBase as any).recoveryFreshnessReasonCode)]
              : (((mergedBase.fundSummary as any)?.recoveryFreshnessReasonCode) && (mergedBase.fundSummary as any).recoveryFreshnessReasonCode !== 'ok')
                ? [String((mergedBase.fundSummary as any).recoveryFreshnessReasonCode)]
                : [];
        const recoveryFreshnessReasonCode = String(
          (mergedBase as any).recoveryFreshnessReasonCode
          || recoveryFreshnessReasonCodes[0]
          || (mergedBase.fundSummary as any)?.recoveryFreshnessReasonCode
          || 'ok'
        );
        const recoveryFreshnessClass = String(
          (mergedBase as any).recoveryFreshnessClass
          || (mergedBase.fundSummary as any)?.recoveryFreshnessClass
          || (recoveryFreshnessReasonCodes.length ? 'unknown' : 'current')
        );
        const recoveryFreshnessNextAction = String(
          (mergedBase as any).recoveryFreshnessNextAction
          || (mergedBase.fundSummary as any)?.recoveryFreshnessNextAction
          || ''
        );
        const recoveryReady = Boolean(
          typeof mergedBase.recoveryReady === 'boolean'
            ? mergedBase.recoveryReady
            : typeof mergedBase.fundSummary?.recoveryReady === 'boolean'
              ? mergedBase.fundSummary.recoveryReady
              : recoveryStatus === 'ready'
        );
        const recoveryHistoryComponent = String((mergedBase as any).recoveryHistoryComponent || (mergedBase.fundSummary as any)?.recoveryHistoryComponent || '');
        const recoveryHistoryStatus = String((mergedBase as any).recoveryHistoryStatus || (mergedBase.fundSummary as any)?.recoveryHistoryStatus || (recoveryReady ? 'steady' : 'unknown'));
        const recoveryDegradedSinceTsMs = Number((mergedBase as any).recoveryDegradedSinceTsMs || (mergedBase.fundSummary as any)?.recoveryDegradedSinceTsMs || 0);
        const recoveryRecoveredAtTsMs = Number((mergedBase as any).recoveryRecoveredAtTsMs || (mergedBase.fundSummary as any)?.recoveryRecoveredAtTsMs || 0);
        const recoveryDegradedDurationMs = Number((mergedBase as any).recoveryDegradedDurationMs || (mergedBase.fundSummary as any)?.recoveryDegradedDurationMs || 0);
        const recoveryDegradedCount = Number((mergedBase as any).recoveryDegradedCount || (mergedBase.fundSummary as any)?.recoveryDegradedCount || 0);
        const recoveryLastHealthyTsMs = Number((mergedBase as any).recoveryLastHealthyTsMs || (mergedBase.fundSummary as any)?.recoveryLastHealthyTsMs || 0);
        const recoveryRecoveredRecently = Boolean(typeof (mergedBase as any).recoveryRecoveredRecently === 'boolean' ? (mergedBase as any).recoveryRecoveredRecently : (mergedBase.fundSummary as any)?.recoveryRecoveredRecently);
        const recoveryDegradationSeverityClass = String((mergedBase as any).recoveryDegradationSeverityClass || (mergedBase.fundSummary as any)?.recoveryDegradationSeverityClass || (recoveryHistoryStatus === 'blocked' ? 'blocked' : (recoveryHistoryStatus === 'recovered' && recoveryRecoveredRecently ? 'recovering' : (recoveryHistoryStatus === 'steady' ? 'stable' : 'acute'))));
        const capitalTruthReliabilityReasonCodes = Array.isArray((mergedBase as any).capitalTruthReliabilityReasonCodes) && (mergedBase as any).capitalTruthReliabilityReasonCodes.length
          ? (mergedBase as any).capitalTruthReliabilityReasonCodes
          : Array.isArray((mergedBase.fundSummary as any)?.capitalTruthReliabilityReasonCodes) && (mergedBase.fundSummary as any).capitalTruthReliabilityReasonCodes.length
            ? (mergedBase.fundSummary as any).capitalTruthReliabilityReasonCodes
            : [];
        const capitalTruthReliabilityClass = String((mergedBase as any).capitalTruthReliabilityClass || (mergedBase.fundSummary as any)?.capitalTruthReliabilityClass || 'stable');
        const capitalTruthReliabilityReasonCode = String((mergedBase as any).capitalTruthReliabilityReasonCode || capitalTruthReliabilityReasonCodes[0] || (mergedBase.fundSummary as any)?.capitalTruthReliabilityReasonCode || (capitalTruthReliabilityClass !== 'stable' ? `capital_truth_reliability_${capitalTruthReliabilityClass}` : 'ok'));
        const capitalTruthRecoveredFragile = Boolean(typeof (mergedBase as any).capitalTruthRecoveredFragile === 'boolean' ? (mergedBase as any).capitalTruthRecoveredFragile : (mergedBase.fundSummary as any)?.capitalTruthRecoveredFragile);
        const internalPrimeReliabilityReasonCodes = Array.isArray((mergedBase as any).internalPrimeReliabilityReasonCodes) && (mergedBase as any).internalPrimeReliabilityReasonCodes.length
          ? (mergedBase as any).internalPrimeReliabilityReasonCodes
          : Array.isArray((mergedBase.fundSummary as any)?.internalPrimeReliabilityReasonCodes) && (mergedBase.fundSummary as any).internalPrimeReliabilityReasonCodes.length
            ? (mergedBase.fundSummary as any).internalPrimeReliabilityReasonCodes
            : [];
        const internalPrimeReliabilityClass = String((mergedBase as any).internalPrimeReliabilityClass || (mergedBase.fundSummary as any)?.internalPrimeReliabilityClass || 'stable');
        const internalPrimeReliabilityReasonCode = String((mergedBase as any).internalPrimeReliabilityReasonCode || internalPrimeReliabilityReasonCodes[0] || (mergedBase.fundSummary as any)?.internalPrimeReliabilityReasonCode || (internalPrimeReliabilityClass !== 'stable' ? `internal_prime_reliability_${internalPrimeReliabilityClass}` : 'ok'));
        const internalPrimeRecoveredFragile = Boolean(typeof (mergedBase as any).internalPrimeRecoveredFragile === 'boolean' ? (mergedBase as any).internalPrimeRecoveredFragile : (mergedBase.fundSummary as any)?.internalPrimeRecoveredFragile);
        const recoveryReliabilityReasonCodes = Array.isArray((mergedBase as any).recoveryReliabilityReasonCodes) && (mergedBase as any).recoveryReliabilityReasonCodes.length
          ? (mergedBase as any).recoveryReliabilityReasonCodes
          : Array.isArray((mergedBase.fundSummary as any)?.recoveryReliabilityReasonCodes) && (mergedBase.fundSummary as any).recoveryReliabilityReasonCodes.length
            ? (mergedBase.fundSummary as any).recoveryReliabilityReasonCodes
            : [];
        const recoveryReliabilityClass = String((mergedBase as any).recoveryReliabilityClass || (mergedBase.fundSummary as any)?.recoveryReliabilityClass || 'stable');
        const recoveryReliabilityReasonCode = String((mergedBase as any).recoveryReliabilityReasonCode || recoveryReliabilityReasonCodes[0] || (mergedBase.fundSummary as any)?.recoveryReliabilityReasonCode || (recoveryReliabilityClass !== 'stable' ? `recovery_reliability_${recoveryReliabilityClass}` : 'ok'));
        const recoveryReliabilityNextAction = String((mergedBase as any).recoveryReliabilityNextAction || (mergedBase.fundSummary as any)?.recoveryReliabilityNextAction || recoveryNextAction || recoveryFreshnessNextAction || '');
        const recoveryRecoveredFragile = Boolean(typeof (mergedBase as any).recoveryRecoveredFragile === 'boolean' ? (mergedBase as any).recoveryRecoveredFragile : (mergedBase.fundSummary as any)?.recoveryRecoveredFragile);
        const executionAdvisoryReasonCodes = Array.isArray((mergedBase as any).executionAdvisoryReasonCodes) && (mergedBase as any).executionAdvisoryReasonCodes.length
          ? (mergedBase as any).executionAdvisoryReasonCodes.map((x: unknown) => String(x))
          : Array.isArray((mergedBase.fundSummary as any)?.recoveryReliabilityReasonCodes) && (mergedBase.fundSummary as any).recoveryReliabilityReasonCodes.length
            ? (mergedBase.fundSummary as any).recoveryReliabilityReasonCodes.map((x: unknown) => String(x))
            : (((mergedBase as any).executionAdvisoryReasonCode) && (mergedBase as any).executionAdvisoryReasonCode !== 'ok')
              ? [String((mergedBase as any).executionAdvisoryReasonCode)]
              : (((mergedBase.fundSummary as any)?.recoveryReliabilityReasonCode) && (mergedBase.fundSummary as any).recoveryReliabilityReasonCode !== 'ok')
                ? [String((mergedBase.fundSummary as any).recoveryReliabilityReasonCode)]
                : [];
        const executionAdvisoryClass = String(
          (mergedBase as any).executionAdvisoryClass
          || (mergedBase.fundSummary as any)?.recoveryReliabilityClass
          || 'stable'
        );
        const executionAdvisorySeverity = String(
          (mergedBase as any).executionAdvisorySeverity
          || (executionAdvisoryClass === 'stable' ? 'normal' : executionAdvisoryClass === 'cautious' ? 'caution' : 'warning')
        );
        const executionAdvisoryReasonCode = String(
          (mergedBase as any).executionAdvisoryReasonCode
          || executionAdvisoryReasonCodes[0]
          || ((mergedBase.fundSummary as any)?.recoveryReliabilityReasonCode)
          || (executionAdvisoryClass !== 'stable' ? `recovery_reliability_${executionAdvisoryClass}` : 'ok')
        );
        const executionAdvisoryNextAction = String(
          (mergedBase as any).executionAdvisoryNextAction
          || (mergedBase.fundSummary as any)?.recoveryReliabilityNextAction
          || recoveryReliabilityNextAction
          || recoveryNextAction
          || ''
        );
        const executionAdvisoryActive = Boolean(
          typeof (mergedBase as any).executionAdvisoryActive === 'boolean'
            ? (mergedBase as any).executionAdvisoryActive
            : executionAdvisoryClass !== 'stable'
        );
        const holdLine = commandCenterHoldLine({
          ...mergedBase,
          holdReasonCode,
          holdReasonCodes,
          suggestedNextAction,
          executionAdvisoryActive,
          executionAdvisorySeverity,
          executionAdvisoryClass,
          executionAdvisoryReasonCode,
          executionAdvisoryReasonCodes,
          executionAdvisoryNextAction,
          executionAdvisoryActive,
          executionAdvisorySeverity,
          executionAdvisoryClass,
          executionAdvisoryReasonCode,
          executionAdvisoryReasonCodes,
          executionAdvisoryNextAction,
        });
        const pausedReason = mergedBase.pausedReason || (holdLine ? `Hold is active because ${holdLine}.` : '');
        return {
          ...mergedBase,
          summaryContract: snapshotSummaryContract,
          projectionCompatibility: mergedProjectionCompatibility,
          pausedReason,
          holdReasonCode,
          holdReasonCodes,
          suggestedNextAction,
          recoveryReady,
          recoveryStatus,
          recoveryReasonCode,
          recoveryReasonCodes,
          recoveryNextAction,
          recoveryFreshnessClass,
          recoveryFreshnessReasonCode,
          recoveryFreshnessReasonCodes,
          recoveryFreshnessNextAction,
          recoveryHistoryComponent,
          recoveryHistoryStatus,
          recoveryDegradedSinceTsMs,
          recoveryRecoveredAtTsMs,
          recoveryDegradedDurationMs,
          recoveryDegradedCount,
          recoveryLastHealthyTsMs,
          recoveryRecoveredRecently,
          recoveryDegradationSeverityClass,
          capitalTruthReliabilityClass,
          capitalTruthReliabilityReasonCode,
          capitalTruthReliabilityReasonCodes,
          capitalTruthRecoveredFragile,
          internalPrimeReliabilityClass,
          internalPrimeReliabilityReasonCode,
          internalPrimeReliabilityReasonCodes,
          internalPrimeRecoveredFragile,
          recoveryReliabilityClass,
          recoveryReliabilityReasonCode,
          recoveryReliabilityReasonCodes,
          recoveryReliabilityNextAction,
          recoveryRecoveredFragile,
        };
      } catch {
        // Backwards compatible fallback for older backends.
        const legacy = (await apiGet(baseUrl, "/api/state", headers)) as any;
        const autoTrading = !!legacy?.metrics?.auto_trading;
        const legacyProjectionCompatibility = mergeProjectionCompatibility({
          commandCenter: evaluateProjectionCompatibility(undefined, {
            truthFamily: 'command_center',
            readModel: 'command_center_summary_projection_v1',
            fallbackUsed: true,
          }),
        });
        const legacyProjectionAlert = projectionCompatibilityAlert(legacyProjectionCompatibility, { tsMs: Date.now() });
        return {
          ...DEMO_SNAPSHOT,
          ok: true,
          projectionCompatibility: legacyProjectionCompatibility,
          alerts: legacyProjectionAlert ? [legacyProjectionAlert, ...DEMO_SNAPSHOT.alerts] : DEMO_SNAPSHOT.alerts,
          controlMode: autoTrading ? "auto" : "view_only",
          pausedReason: autoTrading ? "" : "Legacy backend reports auto trading disabled.",
          dataSource: "backend",
          liveMode: "backend-mock",
          sourceLabel: String((deploy as any)?.brand?.name || "x∆v"),
          portfolio: {
            ...DEMO_SNAPSHOT.portfolio,
            updatedAtMs: Date.now(),
            state: autoTrading ? "active" : "paused",
          },
        };
      }
    },
    setControls: async (patch: ControlPatch, reason: string) => {
      return (await apiPost(baseUrl, "/api/commandcenter/control", { patch, reason }, headers)) as any;
    },
    explain: async () => {
      try {
        return (await apiGet(baseUrl, "/api/system/capital/explain", headers)) as any;
      } catch {
        return (await apiGet(baseUrl, "/api/commandcenter/explain", headers)) as any;
      }
    },
    auditTail: async (limit: number) => {
      return (await apiGet(baseUrl, `/api/commandcenter/audit/tail?limit=${encodeURIComponent(String(limit))}`, headers)) as any;
    },
  };
}
