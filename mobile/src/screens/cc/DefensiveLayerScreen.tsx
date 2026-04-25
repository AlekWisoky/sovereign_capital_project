import React, { useMemo, useState } from "react";
import { View, Text, ScrollView, Pressable } from "react-native";
import { useTheme } from "../../utils/useTheme";
import { pageContentContainerStyle, pageShellStyle } from '../../utils/layout';
import { SurfaceCard } from "../../components/v2/SurfaceCard";
import { TopStatusBar } from "../../components/cc/TopStatusBar";
import { ConfirmReasonDialog } from "../../components/cc/ConfirmReasonDialog";
import { useCommandCenter } from "../../commandCenter/useCommandCenter";
import type { ControlPatch } from "../../commandCenter/types";
import { useStore } from "../../state/store";
import { stressEvaluate } from "../../api/client";
import { killSwitchReasons, liveFragilitySummary } from '../../commandCenter/executionSummary';

type Action = { key: string; title: string; body: string; patch: ControlPatch; tone?: "neutral" | "danger" };

type StressResult = { scenario: string; deltaNavUsd: number; projectedNavUsd: number; exposureClampPct: number; triggeredBreaker: string } | null;

export function DefensiveLayerScreen() {
  const theme = useTheme();
  const cc = useCommandCenter();
  const { state } = useStore();
  const snap = cc.snapshot;
  const [confirm, setConfirm] = useState<Action | null>(null);
  const [status, setStatus] = useState<string>("");
  const [stress, setStress] = useState<StressResult>(null);

  const actions: Action[] = useMemo(
    () => [
      { key: "pause", title: "Pause AI", body: "Stops autonomous execution. Manual actions remain available.", patch: { paused: true }, tone: "danger" },
      { key: "freeze_alloc", title: "Freeze allocations", body: "AI can still trade, but cannot move capital between strategies.", patch: { allocationsFrozen: true } },
      { key: "reduce", title: "Reduce exposure 50%", body: "Clamps notional sizing by 50% (defensive).", patch: { reduceExposureHalf: true } },
      { key: "defensive", title: "Enter Defensive Mode", body: "Aggressive risk clamps + tighter vetoes; still runs flashloan atomic.", patch: { defensiveMode: true } },
    ],
    [],
  );

  async function doConfirm(reason: string) {
    if (!confirm) return;
    setStatus("Applying…");
    try {
      const r = await cc.setControls(confirm.patch, reason);
      if (!r.ok) setStatus(r.error ? `Failed · ${r.error}` : "Failed");
      else {
        setStatus("Applied.");
        void cc.refresh();
      }
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    } finally {
      setConfirm(null);
    }
  }

  async function runStress(scenario: string) {
    if (cc.source !== "backend") {
      setStress({ scenario, deltaNavUsd: -12.5, projectedNavUsd: Math.max(0, (snap?.portfolio.navUsd ?? 100) - 12.5), exposureClampPct: 80, triggeredBreaker: scenario === "gas_5x" ? "gasAnomalyBreaker" : "" });
      return;
    }
    try {
      const res = await stressEvaluate(state.baseUrl, scenario, state.role === "operator" ? state.adminKey : undefined);
      setStress({
        scenario: String((res as any)?.scenario ?? scenario),
        deltaNavUsd: Number((res as any)?.deltaNavUsd ?? 0),
        projectedNavUsd: Number((res as any)?.projectedNavUsd ?? 0),
        exposureClampPct: Number((res as any)?.exposureClampPct ?? 100),
        triggeredBreaker: String((res as any)?.triggeredBreaker ?? ""),
      });
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  const risk = snap?.risk;
  const meter = risk ? Math.max(0, Math.min(100, risk.composite)) : 0;
  const w = `${meter}%`;
  const drawdown = snap?.execution?.drawdown;
  const hardStop = drawdown?.hardStop;
  const killReasons = killSwitchReasons(snap);
  const fragility = liveFragilitySummary(snap);

  const scenarios = [
    ["liquidity_drop_50", "Liquidity -50%"],
    ["slippage_3x", "Slippage x3"],
    ["gas_5x", "Gas x5"],
    ["noise_injection", "Noise injection"],
  ] as const;

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 40)}>
      <TopStatusBar title="Defensive Layer" subtitle="Kill switches · circuit breakers · tail-risk" rightTag={cc.source === "backend" ? "BACKEND" : "DEMO"} live={cc.source === "backend"} />

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="cyan">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Real-time Risk Meter</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Composite risk score: <Text style={{ color: theme.colors.cyan, fontWeight: "900" }}>{meter.toFixed(0)}</Text> / 100
        </Text>

        <View style={{ marginTop: theme.spacing.md, height: 14, borderRadius: theme.radii.pill, overflow: "hidden", borderWidth: 1, borderColor: theme.colors.border }}>
          <View style={{ width: w, height: 14, backgroundColor: meter < 40 ? theme.colors.good : meter < 70 ? theme.colors.warn : theme.colors.danger }} />
        </View>

        {risk ? (
          <View style={{ marginTop: theme.spacing.md }}>
            <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>
              Caps · daily loss {risk.caps.maxDailyLossPct}% · max exposure {risk.caps.maxExposurePct}% · sandbox {risk.caps.sandboxCapPct}% · probation {risk.caps.probationCapPct}%
            </Text>
            <Text style={{ color: theme.colors.textFaint, marginTop: 6, ...theme.typography.mono }}>
              Breakers · drawdown {risk.breakers.drawdownBreaker ? "ON" : "off"} · gas {risk.breakers.gasAnomalyBreaker ? "ON" : "off"} · drift {risk.breakers.driftBreaker ? "ON" : "off"}
            </Text>
          </View>
        ) : null}
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="violet">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Tail Risk Simulator</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Deterministic stress engine with exposure clamp projections and breaker hints.
        </Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: theme.spacing.md }}>
          {scenarios.map(([key, label]) => (
            <Pressable key={key} onPress={() => void runStress(key)} style={{ paddingVertical: 10, paddingHorizontal: 12, borderRadius: theme.radii.pill, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
              <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>{label}</Text>
            </Pressable>
          ))}
        </View>
        {stress ? (
          <View style={{ marginTop: theme.spacing.md }}>
            <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>
              Scenario {stress.scenario} → Δ NAV ${stress.deltaNavUsd.toFixed(2)} · projected NAV ${stress.projectedNavUsd.toFixed(2)} · clamp {stress.exposureClampPct.toFixed(0)}%
            </Text>
            {stress.triggeredBreaker ? <Text style={{ color: theme.colors.warn, marginTop: 6, ...theme.typography.body }}>Breaker hint: {stress.triggeredBreaker}</Text> : null}
          </View>
        ) : null}
      </SurfaceCard>


      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow={hardStop?.active ? 'cyan' : 'none'}>
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Live Hard Stop + Suppression State</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>Operator-facing drawdown stop, kill-switch reasons, and adversarial fragility summary.</Text>
        <Text style={{ color: hardStop?.active ? theme.colors.danger : theme.colors.textFaint, marginTop: theme.spacing.md, ...theme.typography.mono }}>
          Hard stop: {hardStop?.active ? 'ACTIVE' : 'clear'} · drawdown {(Number(drawdown?.drawdownPct ?? 0)).toFixed(2)}% · intraday loss ${Number(drawdown?.intradayLossUsd ?? 0).toFixed(2)}
        </Text>
        {Array.isArray(hardStop?.reason_codes) && hardStop!.reason_codes!.length ? (
          <Text style={{ color: theme.colors.warn, marginTop: 6, ...theme.typography.body }}>Reasons: {hardStop!.reason_codes!.join(', ')}</Text>
        ) : null}
        <Text style={{ color: theme.colors.textFaint, marginTop: 10, ...theme.typography.mono }}>
          Fragility · route {fragility.routeFamily || 'none'} · interference {(fragility.fragility * 100).toFixed(0)}% · private lane {fragility.requiresPrivateLane ? 'required' : 'optional'} · pending {fragility.pendingCount}
        </Text>
        <Text style={{ color: theme.colors.textFaint, marginTop: 4, ...theme.typography.mono }}>
          Flash provider {fragility.provider || 'n/a'} · fallback {fragility.fallbackReady ? 'ready' : 'none'}
        </Text>
        {fragility.routeInvalidCauses.length ? (
          <View style={{ marginTop: 10 }}>
            {fragility.routeInvalidCauses.slice(0, 4).map((reason) => (
              <Text key={reason} style={{ color: theme.colors.warn, marginTop: 4, ...theme.typography.body }}>• {reason}</Text>
            ))}
          </View>
        ) : null}
        {killReasons.length ? (
          <View style={{ marginTop: 10 }}>
            {killReasons.slice(0, 4).map((reason) => (
              <Text key={reason} style={{ color: theme.colors.danger, marginTop: 4, ...theme.typography.body }}>• {reason}</Text>
            ))}
          </View>
        ) : (
          <Text style={{ color: theme.colors.textFaint, marginTop: 10 }}>No active suppressions.</Text>
        )}
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Kill Switch Panel</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Dangerous actions require a reason and are audit-logged. Auto-trading still functions in “freeze allocations” mode.
        </Text>

        <View style={{ marginTop: theme.spacing.md, gap: 10 }}>
          {actions.map((a) => (
            <Pressable
              key={a.key}
              onPress={() => setConfirm(a)}
              style={{
                paddingVertical: 14,
                paddingHorizontal: 12,
                borderRadius: theme.radii.lg,
                borderWidth: 1,
                borderColor: theme.colors.border,
                backgroundColor: theme.colors.surface1,
                flexDirection: "row",
                justifyContent: "space-between",
              }}
            >
              <View style={{ flex: 1, paddingRight: 12 }}>
                <Text style={{ color: a.tone === "danger" ? theme.colors.danger : theme.colors.text, fontWeight: "900" }}>{a.title}</Text>
                <Text style={{ color: theme.colors.textMuted, marginTop: 4, ...theme.typography.body }}>{a.body}</Text>
              </View>
              <Text style={{ color: theme.colors.cyan, fontWeight: "900" }}>Apply</Text>
            </Pressable>
          ))}
        </View>
        {status ? <Text style={{ color: theme.colors.textFaint, marginTop: theme.spacing.md }}>{status}</Text> : null}
      </SurfaceCard>

      <ConfirmReasonDialog
        visible={!!confirm}
        title={confirm?.title ?? "Confirm"}
        body={confirm?.body ?? ""}
        tone={confirm?.tone ?? "neutral"}
        requireReason
        confirmText="Confirm"
        cancelText="Cancel"
        onCancel={() => setConfirm(null)}
        onConfirm={doConfirm}
      />
    </ScrollView>
  );
}
