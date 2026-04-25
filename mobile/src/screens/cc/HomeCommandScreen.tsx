import React, { useEffect, useMemo, useState } from "react";
import { View, Text, ScrollView, Pressable, TextInput } from "react-native";
import { useTheme } from "../../utils/useTheme";
import { launchWhyNotOverflowCount, launchWhyNotPreview } from '../../utils/launch';
import { fundHealthHoldLine, fundHealthRecoveryFreshnessLine, fundHealthRecoveryHistoryLine, fundHealthRecoveryReliabilityLine } from '../../utils/fund';
import { commandCenterExecutionAdvisoryLine, commandCenterHoldLine, commandCenterRecoveryHistoryLine, commandCenterRecoveryLine, commandCenterRecoveryFreshnessLine, commandCenterRecoveryReliabilityLine } from '../../utils/command';
import { pageContentContainerStyle, pageShellStyle } from '../../utils/layout';
import { SurfaceCard } from "../../components/v2/SurfaceCard";
import { StatTile } from "../../components/v2/StatTile";
import { SegmentedTabs } from "../../components/v2/SegmentedTabs";
import { TopStatusBar } from "../../components/cc/TopStatusBar";
import { SystemStateBadge } from "../../components/cc/SystemStateBadge";
import { ExposureBar } from "../../components/cc/ExposureBar";
import { LiveModeBanner } from "../../components/cc/LiveModeBanner";
import { useCommandCenter } from "../../commandCenter/useCommandCenter";
import type { AggressionMode, ControlMode } from "../../commandCenter/types";
import { enableNextFamily, pauseLaunchFamily, setLaunchMode } from "../../api/client";
import { fetchWealthGoal, setWealthGoal } from "../../api/client";
import { useStore } from "../../state/store";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import type { HomeStackParamList } from "../../navigation/HomeStack";

function pct(n: number): string {
  const s = (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
  return s;
}

function formatMode(mode: ControlMode | undefined): string {
  if (mode === "auto") return "Auto";
  if (mode === "assist") return "Assist";
  return "View Only";
}

function safeNum(s: string, fallback: number): number {
  const n = Number(String(s || "").trim());
  return Number.isFinite(n) ? n : fallback;
}

export function HomeCommandScreen() {
  const theme = useTheme();
  const cc = useCommandCenter();
  const { state } = useStore();
  const snap = cc.snapshot;
  const [tab, setTab] = useState("Command");
  const [goalPct, setGoalPct] = useState("8");
  const [goalDays, setGoalDays] = useState("14");
  const [riskTolerance, setRiskTolerance] = useState<"conservative" | "moderate" | "aggressive">("moderate");
  const [status, setStatus] = useState("");
  const nav = useNavigation<NativeStackNavigationProp<HomeStackParamList>>();
  const commandExecutionAdvisoryLine = useMemo(() => commandCenterExecutionAdvisoryLine(snap), [snap]);

  const controlMode = useMemo<ControlMode>(() => {
    return (snap?.controlMode ?? snap?.governance.controlMode ?? (snap?.governance.paused ? "view_only" : "assist")) as ControlMode;
  }, [snap]);

  const rightTag = useMemo(() => {
    if (!snap) return "Sovereign Capital";
    return `Mode ${formatMode(controlMode)} · NAV $${snap.portfolio.navUsd.toFixed(2)}`;
  }, [snap, controlMode]);

  const aggressionMode = (snap?.governance.aggressionMode ?? "balanced") as AggressionMode;

  const aiSuggestedTargetPct = useMemo(() => {
    if (snap?.wealthGoal?.suggestedNextTargetPct) return snap.wealthGoal.suggestedNextTargetPct;
    const sevenDay = snap?.portfolio.pct7d ?? 0;
    const base = Math.max(4, sevenDay > 0 ? sevenDay * 1.35 + 2 : 6);
    return Number(base.toFixed(2));
  }, [snap]);

  useEffect(() => {
    if (!snap?.wealthGoal) return;
    const goal = snap.wealthGoal;
    setGoalPct(String(goal.targetReturnPct || 0));
    setGoalDays(String(goal.timeframeDays || 14));
    const risk = String(goal.riskTolerance || "moderate").toLowerCase();
    if (risk === "conservative" || risk === "aggressive" || risk === "moderate") {
      setRiskTolerance(risk);
    }
  }, [snap?.wealthGoal]);

  useEffect(() => {
    if (cc.source !== "backend") return;
    if (snap?.wealthGoal) return;
    let cancelled = false;
    (async () => {
      try {
        const goal = await fetchWealthGoal(state.baseUrl, state.role === "operator" ? state.adminKey : undefined);
        if (cancelled) return;
        const g = (goal as Record<string, any>)?.goal;
        if (g) {
          setGoalPct(String(g.target_return_percentage ?? 0));
          setGoalDays(String(Math.max(1, Math.round(Number(g.time_horizon_seconds ?? 0) / 86400) || 14)));
          const risk = String(g.risk_tolerance || "moderate").toLowerCase();
          if (risk === "conservative" || risk === "aggressive" || risk === "moderate") {
            setRiskTolerance(risk);
          }
        }
      } catch {
        // leave local defaults in place
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [cc.source, snap?.wealthGoal, state.baseUrl, state.adminKey, state.role]);

  async function setMode(modeNext: ControlMode) {
    setStatus(`Switching to ${formatMode(modeNext)}…`);
    try {
      const patch: any = { controlMode: modeNext };
      if (modeNext === "view_only") patch.paused = true;
      if (modeNext === "assist") patch.paused = false;
      if (modeNext === "auto") patch.paused = false;
      const res = await cc.setControls(patch, `Home control mode → ${modeNext}`);
      if (!res.ok) {
        setStatus(res.error ? `Failed · ${res.error}` : "Failed");
        return;
      }
      await cc.refresh();
      setStatus(`Now in ${formatMode(modeNext)} mode.`);
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  async function saveGoal() {
    const target = safeNum(goalPct, 8);
    const days = Math.max(1, Math.round(safeNum(goalDays, 14)));
    setStatus("Saving goal…");
    try {
      if (cc.source !== "backend") {
        setStatus("Goal saved locally in demo mode. Connect backend to persist it.");
        return;
      }
      const res = await setWealthGoal(
        state.baseUrl,
        {
          target_return_percentage: target,
          time_horizon_seconds: days * 86400,
          risk_tolerance: riskTolerance,
          reason: "Home wealth goal update",
        },
        state.role === "operator" ? state.adminKey : undefined
      );
      const ok = Boolean((res as Record<string, unknown>)?.ok);
      if (!ok) {
        setStatus("Goal update failed.");
        return;
      }
      await cc.refresh();
      setStatus(`Goal set to ${target.toFixed(2)}% over ${days} days.`);
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  function applySuggestion() {
    const next = snap?.wealthGoal?.goalAchieved ? snap.wealthGoal?.suggestedNextTargetPct ?? aiSuggestedTargetPct : aiSuggestedTargetPct;
    setGoalPct(String(next));
    setGoalDays(String(snap?.wealthGoal?.timeframeDays ?? 14));
    if ((snap?.portfolio.drawdownPct ?? 0) > 4) setRiskTolerance("conservative");
    else if ((snap?.portfolio.pct7d ?? 0) > 4) setRiskTolerance("aggressive");
    else setRiskTolerance("moderate");
    setStatus(`AI goal suggestion loaded: ${Number(next).toFixed(2)}%.`);
  }

  const wealthProgress = Math.max(0, Math.min(100, Number(snap?.wealthGoal?.progressPct ?? 0)));
  const wealthExplain = typeof snap?.wealthGoal?.explanation?.why_posture === 'string'
    ? String(snap?.wealthGoal?.explanation?.why_posture)
    : typeof snap?.wealthGoal?.explanation?.why_next_goal === 'string'
      ? String(snap?.wealthGoal?.explanation?.why_next_goal)
      : '';

  const blockedLaunchLines = useMemo(() => launchWhyNotPreview(snap?.launch, 2), [snap?.launch]);
  const blockedLaunchOverflow = useMemo(() => launchWhyNotOverflowCount(snap?.launch, 2), [snap?.launch]);
  const fundHoldLine = useMemo(() => fundHealthHoldLine(snap?.fundSummary), [snap?.fundSummary]);
  const fundRecoveryHistoryLine = useMemo(() => fundHealthRecoveryHistoryLine(snap?.fundSummary), [snap?.fundSummary]);
  const fundRecoveryFreshnessLine = useMemo(() => fundHealthRecoveryFreshnessLine(snap?.fundSummary), [snap?.fundSummary]);
  const fundRecoveryReliabilityLine = useMemo(() => fundHealthRecoveryReliabilityLine(snap?.fundSummary), [snap?.fundSummary]);
  const commandHoldLine = useMemo(() => commandCenterHoldLine(snap), [snap]);
  const commandRecoveryLine = useMemo(() => commandCenterRecoveryLine(snap), [snap]);
  const commandRecoveryHistoryLine = useMemo(() => commandCenterRecoveryHistoryLine(snap), [snap]);
  const commandRecoveryFreshnessLine = useMemo(() => commandCenterRecoveryFreshnessLine(snap), [snap]);
  const commandRecoveryReliabilityLine = useMemo(() => commandCenterRecoveryReliabilityLine(snap), [snap]);

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 140)}>
      <TopStatusBar title="x∆v · Capital Command" subtitle="Sovereign Capital · AI controls, goals, and live system posture" rightTag={rightTag} live={cc.source === "backend"} />

      <View style={{ height: theme.spacing.md }} />
      <LiveModeBanner mode={(snap?.liveMode ?? (cc.source === "backend" ? "backend-mock" : "demo")) as any} sourceLabel={snap?.sourceLabel} />
      <View style={{ height: theme.spacing.md }} />
      <View style={{ flexDirection: "row", gap: 10, marginBottom: theme.spacing.md }}>
        <Pressable onPress={() => nav.navigate("Dash")} style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1, alignItems: "center" }}>
          <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>Dash</Text>
        </Pressable>
        <Pressable onPress={() => nav.navigate("Tracker")} style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.cyan, alignItems: "center" }}>
          <Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>Tracker</Text>
        </Pressable>
      </View>
      <SegmentedTabs options={["Command", "Market", "News"] as const} value={tab as any} onChange={setTab as any} />

      {snap?.fundSummary ? (
        <>
          <View style={{ height: theme.spacing.md }} />
          <SurfaceCard>
            <Text style={{ color: theme.colors.text, ...theme.typography.h2 }}>Fund Health</Text>
            <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>
              Stage {snap.fundSummary.fundStage} · Risk {snap.fundSummary.riskPosture} · Score {snap.fundSummary.riskScore.toFixed(2)}
            </Text>
            {fundHoldLine ? <Text style={{ color: theme.colors.warn, marginTop: 6 }}>Hold now: {fundHoldLine}</Text> : null}
            {fundRecoveryHistoryLine ? <Text style={{ color: theme.colors.textFaint, marginTop: 4 }}>Recovery history: {fundRecoveryHistoryLine}</Text> : null}
            {fundRecoveryFreshnessLine ? <Text style={{ color: theme.colors.textFaint, marginTop: 4 }}>Recovery freshness: {fundRecoveryFreshnessLine}</Text> : null}
            {fundRecoveryReliabilityLine ? <Text style={{ color: theme.colors.textFaint, marginTop: 4 }}>Recovery reliability: {fundRecoveryReliabilityLine}</Text> : null}
            <View style={{ flexDirection: 'row', gap: 10, marginTop: theme.spacing.md }}>
              <StatTile label="Capital Quality" value={String((snap.fundSummary.capitalQualityScore ?? 0).toFixed(2))} tone="neutral" />
              <StatTile label="Research Quality" value={String((snap.fundSummary.researchQualityScore ?? 0).toFixed(2))} tone="neutral" />
            </View>
          </SurfaceCard>
        </>
      ) : null}

      {snap?.launch ? (
        <>
          <View style={{ height: theme.spacing.md }} />
          <SurfaceCard>
            <Text style={{ color: theme.colors.text, ...theme.typography.h2 }}>Launch Rollout</Text>
            <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Mode {snap.launch.currentLaunchMode.replace(/_/g, ' ')} · Active {snap.launch.activeFamilies.join(', ')}</Text>
            <Text style={{ color: theme.colors.textFaint, marginTop: 4 }}>Next recommended family: {snap.launch.nextRecommendedFamily ? snap.launch.nextRecommendedFamily.replace(/_/g, ' ') : 'none yet'}</Text>
            {snap.launch.reasons?.length ? <Text style={{ color: theme.colors.textFaint, marginTop: 4 }}>{snap.launch.reasons.join(' · ')}</Text> : null}
            {blockedLaunchLines.length ? <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Blocked now: {blockedLaunchLines.join(' · ')}</Text> : null}
            {blockedLaunchOverflow ? <Text style={{ color: theme.colors.textFaint, marginTop: 4 }}>+{blockedLaunchOverflow} more blocked families in launch detail</Text> : null}
            <View style={{ flexDirection: 'row', gap: 10, marginTop: theme.spacing.md }}>
              {(['V1_ONLY','V1_PLUS_STABLE_ALPHA','STAGED_MULTI_STRATEGY'] as const).map((mode) => {
                const active = snap.launch?.currentLaunchMode === mode;
                return (
                  <Pressable key={mode} onPress={() => void setLaunchMode(state.baseUrl, mode, state.role === 'operator' ? state.adminKey : undefined).then(() => cc.refresh())} style={{ flex: 1, paddingVertical: 10, borderRadius: theme.radii.md, borderWidth: 1, borderColor: active ? theme.colors.violet : theme.colors.border, backgroundColor: active ? theme.colors.surface2 : theme.colors.surface1, alignItems: 'center' }}>
                    <Text style={{ color: active ? theme.colors.text : theme.colors.textMuted, fontWeight: '900', textAlign: 'center' }}>{mode.replace(/_/g, ' ')}</Text>
                  </Pressable>
                );
              })}
            </View>
            <View style={{ flexDirection: 'row', gap: 10, marginTop: theme.spacing.md }}>
              <Pressable onPress={() => void enableNextFamily(state.baseUrl, undefined, state.role === 'operator' ? state.adminKey : undefined).then(() => cc.refresh())} style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.cyan, alignItems: 'center' }}>
                <Text style={{ color: theme.colors.bg0, fontWeight: '900' }}>Enable Next Family</Text>
              </Pressable>
              {snap.launch.nextRecommendedFamily ? (
                <Pressable onPress={() => void pauseLaunchFamily(state.baseUrl, snap.launch!.nextRecommendedFamily, state.role === 'operator' ? state.adminKey : undefined).then(() => cc.refresh())} style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1, alignItems: 'center' }}>
                  <Text style={{ color: theme.colors.textMuted, fontWeight: '900' }}>Pause Family</Text>
                </Pressable>
              ) : null}
            </View>
          </SurfaceCard>
        </>
      ) : null}

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="cyan">
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <View style={{ flex: 1, paddingRight: 12 }}>
            <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>AI Control Deck</Text>
            <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
              Clear start/stop control, 3-state mode selection, and live status without changing the 7-tab architecture.
            </Text>
          </View>
          {snap ? <SystemStateBadge state={snap.portfolio.state} /> : null}
        </View>

        <View style={{ flexDirection: "row", gap: 10, marginTop: theme.spacing.md }}>
          <Pressable
            onPress={() => void setMode("auto")}
            style={{ flex: 1, paddingVertical: 14, borderRadius: theme.radii.md, backgroundColor: theme.colors.cyan, alignItems: "center" }}
          >
            <Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>Start AI</Text>
          </Pressable>
          <Pressable
            onPress={() => void setMode("view_only")}
            style={{
              flex: 1,
              paddingVertical: 14,
              borderRadius: theme.radii.md,
              borderWidth: 1,
              borderColor: theme.colors.danger,
              backgroundColor: "rgba(251, 113, 133, 0.10)",
              alignItems: "center",
            }}
          >
            <Text style={{ color: theme.colors.danger, fontWeight: "900" }}>Stop AI</Text>
          </Pressable>
        </View>

        <View style={{ flexDirection: "row", gap: 10, marginTop: theme.spacing.md }}>
          {(["view_only", "assist", "auto"] as const).map((mode) => {
            const active = controlMode === mode;
            return (
              <Pressable
                key={mode}
                onPress={() => void setMode(mode)}
                style={{
                  flex: 1,
                  paddingVertical: 12,
                  borderRadius: theme.radii.md,
                  borderWidth: 1,
                  borderColor: active ? theme.colors.cyan : theme.colors.border,
                  backgroundColor: active ? theme.colors.surface2 : theme.colors.surface1,
                  alignItems: "center",
                }}
              >
                <Text style={{ color: active ? theme.colors.text : theme.colors.textMuted, fontWeight: "900" }}>
                  {mode === "view_only" ? "View Only" : mode === "assist" ? "Assist" : "Auto"}
                </Text>
              </Pressable>
            );
          })}
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Trading aggression</Text>
          <View style={{ flexDirection: "row", gap: 10, marginTop: 10 }}>
            {(["conservative", "balanced", "aggressive"] as const).map((mode) => {
              const active = aggressionMode === mode;
              return (
                <Pressable
                  key={mode}
                  onPress={() => void cc.setControls({ aggressionMode: mode }, `Aggression mode → ${mode}`).then(() => cc.refresh())}
                  style={{
                    flex: 1,
                    paddingVertical: 10,
                    borderRadius: theme.radii.md,
                    borderWidth: 1,
                    borderColor: active ? theme.colors.violet : theme.colors.border,
                    backgroundColor: active ? theme.colors.surface2 : theme.colors.surface1,
                    alignItems: "center",
                  }}
                >
                  <Text style={{ color: active ? theme.colors.text : theme.colors.textMuted, fontWeight: "900" }}>
                    {mode === "conservative" ? "Conservative" : mode === "balanced" ? "Balanced" : "Aggressive"}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        <View style={{ marginTop: theme.spacing.md, padding: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface1, borderWidth: 1, borderColor: theme.colors.border }}>
          <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>System status</Text>
          <Text style={{ color: theme.colors.text, marginTop: 6, ...theme.typography.body }}>
            Last update {snap ? new Date(snap.portfolio.updatedAtMs).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—"} · Source {(snap?.dataSource ?? cc.source).toUpperCase()} · Mode {formatMode(controlMode)}
          </Text>
          {snap?.rpcDegraded ? <Text style={{ color: theme.colors.warn, marginTop: 6, ...theme.typography.body }}>RPC degraded warning detected. Execution quality may be reduced until health recovers.</Text> : null}
          {snap?.pausedReason ? <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>{(controlMode === "auto" && !snap?.governance.paused) ? "Status detail" : "Why trading is off?"} {snap.pausedReason}</Text> : null}
          {commandHoldLine ? <Text style={{ color: theme.colors.warn, marginTop: 6, ...theme.typography.body }}>Hold detail: {commandHoldLine}</Text> : null}
          {commandRecoveryLine ? <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>Recovery path: {commandRecoveryLine}</Text> : null}
          {commandRecoveryHistoryLine ? <Text style={{ color: theme.colors.textFaint, marginTop: 4, ...theme.typography.body }}>Recovery history: {commandRecoveryHistoryLine}</Text> : null}
          {commandExecutionAdvisoryLine ? <Text style={{ color: theme.colors.warn, marginTop: 4, ...theme.typography.body }}>Execution advisory: {commandExecutionAdvisoryLine}</Text> : null}
          {commandRecoveryFreshnessLine ? <Text style={{ color: theme.colors.textFaint, marginTop: 4, ...theme.typography.body }}>Recovery freshness: {commandRecoveryFreshnessLine}</Text> : null}
          {commandRecoveryReliabilityLine ? <Text style={{ color: theme.colors.textFaint, marginTop: 4, ...theme.typography.body }}>Recovery reliability: {commandRecoveryReliabilityLine}</Text> : null}
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="violet">
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <View style={{ flex: 1, paddingRight: 12 }}>
            <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Wealth Goal Engine</Text>
            <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
              Set profit targets and a timeframe. x∆v uses the goal to coordinate capital posture, then suggests a higher target when the current one is achieved.
            </Text>
          </View>
          <Pressable onPress={applySuggestion} style={{ paddingVertical: 10, paddingHorizontal: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface2 }}>
            <Text style={{ color: theme.colors.text, fontWeight: "900" }}>AI Suggest</Text>
          </Pressable>
        </View>

        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: theme.spacing.sm, marginTop: theme.spacing.md }}>
          <StatTile label="Target" value={`${safeNum(goalPct, 0).toFixed(2)}%`} tone="neutral" />
          <StatTile label="Timeframe" value={`${Math.max(1, Math.round(safeNum(goalDays, 14)))}d`} tone="neutral" />
          <StatTile label="Progress" value={`${snap?.wealthGoal?.progressPct?.toFixed(1) ?? "0.0"}%`} tone={snap?.wealthGoal?.goalAchieved ? "good" : "neutral"} />
          <StatTile label="Current Return" value={`${snap?.wealthGoal?.currentReturnPct?.toFixed(2) ?? "0.00"}%`} tone={(snap?.wealthGoal?.currentReturnPct ?? 0) >= 0 ? "good" : "danger"} />
        </View>

        <View style={{ marginTop: theme.spacing.md, height: 10, borderRadius: 999, backgroundColor: theme.colors.surface1, overflow: 'hidden', borderWidth: 1, borderColor: theme.colors.border }}>
          <View style={{ width: `${wealthProgress}%`, height: '100%', backgroundColor: snap?.wealthGoal?.goalAchieved ? theme.colors.good : theme.colors.violet }} />
        </View>
        <Text style={{ color: theme.colors.textFaint, marginTop: 8, ...theme.typography.body }}>
          {snap?.wealthGoal?.goalAchieved ? `Goal achieved · next suggested ${(snap.wealthGoal.suggestedNextTargetPct?.toFixed(2) ?? aiSuggestedTargetPct.toFixed(2))}%` : `Pacing ${(snap?.wealthGoal?.pacing ?? 'steady').replace(/_/g, ' ')} · aggressiveness cap ${(snap?.wealthGoal?.aggressivenessCap ?? 1).toFixed(2)}`}
        </Text>
        {wealthExplain ? <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>{wealthExplain}</Text> : null}
        {Array.isArray(snap?.wealthGoal?.nextGoalReasons) && snap?.wealthGoal?.nextGoalReasons?.length ? (
          <Text style={{ color: theme.colors.textFaint, marginTop: 6, ...theme.typography.body }}>Next goal logic: {snap?.wealthGoal?.nextGoalReasons?.join(' · ')}</Text>
        ) : null}
        {Array.isArray((snap?.wealthGoal as any)?.nextGoalBlockedReasons) && (snap?.wealthGoal as any)?.nextGoalBlockedReasons?.length ? (
          <Text style={{ color: theme.colors.warn, marginTop: 6, ...theme.typography.body }}>Next-goal blockers: {(snap?.wealthGoal as any)?.nextGoalBlockedReasons?.join(' · ')}</Text>
        ) : null}
        {Array.isArray((snap?.wealthGoal as any)?.goalLadder) && (snap?.wealthGoal as any)?.goalLadder?.length ? (
          <Text style={{ color: theme.colors.textFaint, marginTop: 6, ...theme.typography.body }}>Goal ladder: {(snap?.wealthGoal as any)?.goalLadder?.map((x: number) => `${x.toFixed(2)}%`).join(' → ')}</Text>
        ) : null}
        {((snap?.wealthGoal as any)?.capitalBaseUsd || (snap?.wealthGoal as any)?.executionRealismScore || (snap?.wealthGoal as any)?.stabilityScore) ? (
          <Text style={{ color: theme.colors.textFaint, marginTop: 6, ...theme.typography.body }}>Capital base ${Number((snap?.wealthGoal as any)?.capitalBaseUsd ?? 0).toFixed(2)} · stability {Number((snap?.wealthGoal as any)?.stabilityScore ?? 0).toFixed(2)} · execution realism {Number((snap?.wealthGoal as any)?.executionRealismScore ?? 0).toFixed(2)}</Text>
        ) : null}

        <View style={{ marginTop: theme.spacing.md }}>
          <Text style={{ color: theme.colors.textMuted, ...theme.typography.mono }}>Target return %</Text>
          <TextInput
            value={goalPct}
            onChangeText={setGoalPct}
            keyboardType="decimal-pad"
            placeholder="8"
            placeholderTextColor={theme.colors.textFaint}
            style={{ marginTop: 8, padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, color: theme.colors.text, backgroundColor: theme.colors.surface1 }}
          />
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <Text style={{ color: theme.colors.textMuted, ...theme.typography.mono }}>Timeframe (days)</Text>
          <TextInput
            value={goalDays}
            onChangeText={setGoalDays}
            keyboardType="number-pad"
            placeholder="14"
            placeholderTextColor={theme.colors.textFaint}
            style={{ marginTop: 8, padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, color: theme.colors.text, backgroundColor: theme.colors.surface1 }}
          />
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <Text style={{ color: theme.colors.textMuted, ...theme.typography.mono }}>Risk tolerance</Text>
          <View style={{ flexDirection: "row", gap: 10, marginTop: 8 }}>
            {(["conservative", "moderate", "aggressive"] as const).map((risk) => {
              const active = riskTolerance === risk;
              return (
                <Pressable
                  key={risk}
                  onPress={() => setRiskTolerance(risk)}
                  style={{
                    flex: 1,
                    paddingVertical: 12,
                    borderRadius: theme.radii.md,
                    borderWidth: 1,
                    borderColor: active ? theme.colors.cyan : theme.colors.border,
                    backgroundColor: active ? theme.colors.surface2 : theme.colors.surface1,
                    alignItems: "center",
                  }}
                >
                  <Text style={{ color: active ? theme.colors.text : theme.colors.textMuted, fontWeight: "900" }}>{risk}</Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        <Pressable onPress={() => void saveGoal()} style={{ marginTop: theme.spacing.lg, paddingVertical: 14, borderRadius: theme.radii.md, backgroundColor: theme.colors.cyan, alignItems: "center" }}>
          <Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>Save Profit Goal</Text>
        </Pressable>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />
      {snap ? (
        <SurfaceCard glow="none">
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>System Overview</Text>
            <SystemStateBadge state={snap.portfolio.state} />
          </View>

          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: theme.spacing.sm, marginTop: theme.spacing.md }}>
            <StatTile label="Total NAV" value={`$${snap.portfolio.navUsd.toFixed(2)}`} tone="neutral" />
            <StatTile label="24h" value={pct(snap.portfolio.pct24h)} tone={snap.portfolio.pct24h >= 0 ? "good" : "danger"} />
            <StatTile label="7d" value={pct(snap.portfolio.pct7d)} tone={snap.portfolio.pct7d >= 0 ? "good" : "danger"} />
            <StatTile label="Drawdown" value={pct(-Math.abs(snap.portfolio.drawdownPct))} tone={snap.portfolio.drawdownPct <= 2 ? "neutral" : "warn"} />
          </View>

          <View style={{ marginTop: theme.spacing.lg }}>
            <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>AI Intent Snapshot</Text>
            <Text style={{ color: theme.colors.text, marginTop: 8, ...theme.typography.body }}>{snap.aiIntent.intent}</Text>
            <Text style={{ color: theme.colors.textMuted, marginTop: 8, ...theme.typography.body }}>
              Confidence: <Text style={{ color: theme.colors.cyan, fontWeight: "900" }}>{Math.round(snap.aiIntent.confidence * 100)}%</Text>
              {"  "}· Strategies: {snap.aiIntent.strategies.join(", ")}
            </Text>
          </View>

          <View style={{ marginTop: theme.spacing.lg }}>
            <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Exposure Radar</Text>
            <View style={{ marginTop: 10 }}>
              <ExposureBar exposure={snap.exposure} />
            </View>
          </View>
        </SurfaceCard>
      ) : (
        <SurfaceCard glow="none">
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Loading…</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Using {cc.source} data source.</Text>
          {cc.error ? <Text style={{ color: theme.colors.danger, marginTop: 6 }}>{cc.error}</Text> : null}
        </SurfaceCard>
      )}

      <View style={{ height: theme.spacing.md }} />
      {snap ? (
        <SurfaceCard glow="none">
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Alerts</Text>
            <Pressable onPress={() => void cc.refresh()} style={{ paddingVertical: 6, paddingHorizontal: 10, borderRadius: theme.radii.pill, backgroundColor: theme.colors.surface2 }}>
              <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>Refresh</Text>
            </Pressable>
          </View>
          <View style={{ marginTop: theme.spacing.md }}>
            {snap.alerts.slice(0, 6).map((a) => {
              const tone = a.severity === "danger" ? theme.colors.danger : a.severity === "warn" ? theme.colors.warn : theme.colors.textFaint;
              return (
                <View key={a.id} style={{ paddingVertical: 10, borderTopWidth: 1, borderTopColor: theme.colors.border }}>
                  <Text style={{ color: tone, fontWeight: "900" }}>{a.title}</Text>
                  <Text style={{ color: theme.colors.textMuted, marginTop: 4, ...theme.typography.body }}>{a.detail}</Text>
                </View>
              );
            })}
            {!snap.alerts.length ? <Text style={{ color: theme.colors.textMuted }}>No alerts.</Text> : null}
          </View>
        </SurfaceCard>
      ) : null}

      {status ? <Text style={{ color: theme.colors.textMuted, marginTop: theme.spacing.md, ...theme.typography.mono }}>{status}</Text> : null}
    </ScrollView>
  );
}
