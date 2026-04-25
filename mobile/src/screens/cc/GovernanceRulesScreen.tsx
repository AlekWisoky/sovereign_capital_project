import React, { useMemo, useState } from "react";
import { View, Text, ScrollView, Pressable } from "react-native";
import { useTheme } from "../../utils/useTheme";
import { pageContentContainerStyle, pageShellStyle } from '../../utils/layout';
import { SurfaceCard } from "../../components/v2/SurfaceCard";
import { TopStatusBar } from "../../components/cc/TopStatusBar";
import { ConfirmReasonDialog } from "../../components/cc/ConfirmReasonDialog";
import { ConfirmDialog } from "../../components/v2/ConfirmDialog";
import { useCommandCenter } from "../../commandCenter/useCommandCenter";
import { formatExplainResponse } from "../../commandCenter/executionSummary";
import type { ControlPatch } from "../../commandCenter/types";
import { useStore } from "../../state/store";
import { exportRftEpisodes } from "../../api/client";

type PendingToggle = { title: string; body: string; patch: ControlPatch; tone?: "neutral" | "danger" };

export function GovernanceRulesScreen() {
  const theme = useTheme();
  const cc = useCommandCenter();
  const { state, set } = useStore();
  const snap = cc.snapshot;
  const [pending, setPending] = useState<PendingToggle | null>(null);
  const [explain, setExplain] = useState<string>("");
  const [status, setStatus] = useState<string>("");
  const [exportOpen, setExportOpen] = useState<boolean>(false);

  const rules = snap?.governance;
  const dsLabel = cc.source === "backend" ? "Backend" : "Demo";
  const canExport = cc.source === "backend" && state.role === "operator" && Boolean(state.adminKey);

  async function applyToggle(patch: ControlPatch, reason: string) {
    setStatus("Applying…");
    try {
      const r = await cc.setControls(patch, reason);
      if (!r.ok) setStatus(r.error ? `Failed · ${r.error}` : "Failed");
      else {
        setStatus("Applied.");
        void cc.refresh();
      }
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(null);
    }
  }

  async function runExplain() {
    setStatus("Explaining…");
    try {
      const r = await cc.explain();
      setExplain(formatExplainResponse(r));
      setStatus("");
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  async function doExportEpisodes(reason: string) {
    setExportOpen(false);
    if (!canExport) {
      setStatus("Unlock operator mode and connect to backend before exporting.");
      return;
    }
    setStatus("Exporting RFT episodes…");
    try {
      const res = await exportRftEpisodes(
        state.baseUrl,
        { reason, limit: 500 },
        state.adminKey
      );
      const ok = Boolean((res as Record<string, unknown>)?.ok);
      if (!ok) {
        setStatus(`Export failed · ${String((res as Record<string, unknown>)?.error ?? "unknown")}`);
        return;
      }
      setStatus(`Episodes exported · ${String((res as Record<string, unknown>)?.count ?? 0)} records`);
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  const toggles = useMemo(() => {
    if (!rules) return [] as PendingToggle[];
    const nextCycle = <T extends string>(cur: T | undefined, vals: T[]): T => {
      const i = Math.max(0, vals.indexOf((cur ?? "") as T));
      return vals[(i + 1) % vals.length];
    };
    const sendNext = nextCycle(rules.forceSendMode as any, ["", "protected_rpc", "private", "public"] as any);
    const gasNext = nextCycle(rules.forceGasMode as any, ["", "standard", "fast", "instant"] as any);
    const brainNext = nextCycle(rules.brainMode as any, ["", "off", "baseline", "rl"] as any);
    const aggressionNext = nextCycle((rules.aggressionMode ?? "balanced") as any, ["conservative", "balanced", "aggressive"] as any);
    return [
      {
        title: rules.paused ? "Resume AI" : "Pause AI",
        body: rules.paused ? "Resumes autonomous execution." : "Stops autonomous execution. Manual actions remain possible.",
        patch: { paused: !rules.paused },
        tone: rules.paused ? "neutral" : "danger",
      },
      {
        title: rules.sandboxOnly ? "Disable Sandbox-Only" : "Enable Sandbox-Only",
        body: "Sandbox-only keeps execution constrained; live capital stays protected.",
        patch: { sandboxOnly: !rules.sandboxOnly },
      },
      {
        title: rules.allocationsFrozen ? "Unfreeze allocations" : "Freeze allocations",
        body: "When frozen, auto-trading still functions, but the capital layer cannot move capital between strategies.",
        patch: { allocationsFrozen: !rules.allocationsFrozen },
      },
      {
        title: rules.evolutionFrozen ? "Unfreeze evolution" : "Freeze evolution",
        body: "Freeze evolution prevents strategy mutation/meta evolution. Recommended for v1 stability.",
        patch: { evolutionFrozen: !rules.evolutionFrozen },
      },
      {
        title: rules.mutationEnabled ? "Disable mutation" : "Enable mutation",
        body: "Mutation should remain OFF until alpha is statistically proven.",
        patch: { mutationEnabled: !rules.mutationEnabled },
      },
      {
        title: rules.governanceEnabled ? "Disable governance engine" : "Enable governance engine",
        body: "Governance adds additional constraints and approvals; disable only for debugging with extreme care.",
        patch: { governanceEnabled: !rules.governanceEnabled },
        tone: rules.governanceEnabled ? "danger" : "neutral",
      },
      {
        title: (rules.fullSystemEnabled ?? false) ? "Disable full system" : "Enable full system",
        body: "Full system enables coordinated evolution, governance, reward traces, and mutation staging with safe defaults.",
        patch: { fullSystemEnabled: !(rules.fullSystemEnabled ?? false) },
      },
      {
        title: (rules.metricsEnabled ?? true) ? "Disable metrics" : "Enable metrics",
        body: "Metrics are observability-only. Disabling reduces overhead slightly (recommended only on ultra-low-latency nodes).",
        patch: { metricsEnabled: !(rules.metricsEnabled ?? true) },
      },
      {
        title: (rules.latencyProfilingEnabled ?? true) ? "Disable latency profiling" : "Enable latency profiling",
        body: "Collects p50/p90/p99 loop + execution latency. Observability only; never used for decisions.",
        patch: { latencyProfilingEnabled: !(rules.latencyProfilingEnabled ?? true) },
      },
      {
        title: (rules.rewardTraceEnabled ?? true) ? "Disable reward trace" : "Enable reward trace",
        body: "Logs reward components per decision/trade outcome. Recommended ON for replay verification and grader analysis.",
        patch: { rewardTraceEnabled: !(rules.rewardTraceEnabled ?? true) },
      },
      {
        title: (rules.rftEpisodeExportEnabled ?? false) ? "Disable RFT episode export" : "Enable RFT episode export",
        body: "Admin-gated deterministic episode export for proposal-only reinforcement fine-tuning workflows.",
        patch: { rftEpisodeExportEnabled: !(rules.rftEpisodeExportEnabled ?? false) },
      },
      {
        title: (rules.chaosBreakersEnabled ?? true) ? "Disable anomaly breakers" : "Enable anomaly breakers",
        body: "Gas spikes and RPC error storms can force Defensive Mode. Disabling is not recommended.",
        patch: { chaosBreakersEnabled: !(rules.chaosBreakersEnabled ?? true) },
        tone: (rules.chaosBreakersEnabled ?? true) ? "neutral" : "danger",
      },
      {
        title: (rules.rpcBatchEnabled ?? false) ? "Disable RPC batching" : "Enable RPC batching",
        body: "Batching reduces latency on supportive providers. If your RPC rejects batched JSON, keep OFF.",
        patch: { rpcBatchEnabled: !(rules.rpcBatchEnabled ?? false) },
      },
      {
        title: (rules.kellyEnabled ?? false) ? "Disable Kelly sizing" : "Enable Kelly sizing",
        body: "Kelly sizing increases capital efficiency after sufficient history. Default OFF until explicitly enabled.",
        patch: { kellyEnabled: !(rules.kellyEnabled ?? false) },
      },
      {
        title: (rules.autoReinvestEnabled ?? false) ? "Disable auto-reinvest" : "Enable auto-reinvest",
        body: "Auto-reinvest increases base notional using realized profits. Use with probation caps.",
        patch: { autoReinvestEnabled: !(rules.autoReinvestEnabled ?? false) },
      },
      {
        title: `Cycle aggression mode → ${aggressionNext}`,
        body: "Deterministic treasury/aggression posture. Conservative reduces size pressure; aggressive raises urgency and size caps within governance bounds.",
        patch: { aggressionMode: aggressionNext as any },
      },
      {
        title: `Cycle send mode override → ${sendNext || "(none)"}`,
        body: "Forces send mode at execution time. Operator override wins over planners. Leave NONE for normal behavior.",
        patch: { forceSendMode: sendNext as any },
        tone: sendNext === "public" ? "danger" : "neutral",
      },
      {
        title: `Cycle gas mode override → ${gasNext || "(none)"}`,
        body: "Forces gas preset mode at execution time. Leave NONE for default strategy behavior.",
        patch: { forceGasMode: gasNext as any },
      },
      {
        title: `Cycle brain mode → ${brainNext || "(none)"}`,
        body: "Controls learning/exploration posture. RL is recommended only after alpha is proven + probation staging enabled.",
        patch: { brainMode: brainNext as any },
      },
    ];
  }, [rules]);

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 40)}>
      <TopStatusBar title="Rules" subtitle="Permissions · replay export · immutable change history" rightTag={`Data: ${dsLabel}`} live={cc.source === "backend"} />

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="cyan">
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Rulebook (v1)</Text>
          <View style={{ flexDirection: "row", gap: 10 }}>
            <Pressable
              onPress={() => {
                const next = cc.source === "backend" ? "mock" : "backend";
                cc.setSource(next);
                set({ ccDataSource: next });
              }}
              style={{ paddingVertical: 6, paddingHorizontal: 10, borderRadius: theme.radii.pill, backgroundColor: theme.colors.surface2 }}
            >
              <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>Switch Source</Text>
            </Pressable>
            <Pressable onPress={() => void cc.refresh()} style={{ paddingVertical: 6, paddingHorizontal: 10, borderRadius: theme.radii.pill, backgroundColor: theme.colors.surface2 }}>
              <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>Refresh</Text>
            </Pressable>
          </View>
        </View>

        {rules ? (
          <View style={{ marginTop: theme.spacing.md }}>
            <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Focus: {rules.v1Focus}</Text>
            <Text style={{ color: theme.colors.textFaint, marginTop: 6, ...theme.typography.mono }}>AI authority: {rules.aiAuthority}</Text>
            <Text style={{ color: theme.colors.textFaint, marginTop: 6, ...theme.typography.mono }}>Paused: {rules.paused ? "yes" : "no"} · Sandbox-only: {rules.sandboxOnly ? "yes" : "no"}</Text>
            <Text style={{ color: theme.colors.textFaint, marginTop: 6, ...theme.typography.mono }}>
              Metrics: {(rules.metricsEnabled ?? true) ? "on" : "off"} · Latency: {(rules.latencyProfilingEnabled ?? true) ? "on" : "off"} · Reward trace: {(rules.rewardTraceEnabled ?? true) ? "on" : "off"}
            </Text>
            <Text style={{ color: theme.colors.textFaint, marginTop: 6, ...theme.typography.mono }}>
              RFT export: {(rules.rftEpisodeExportEnabled ?? false) ? "on" : "off"} · Aggression: {rules.aggressionMode || "balanced"} · Full system: {(rules.fullSystemEnabled ?? false) ? "on" : "off"} · Send override: {rules.forceSendMode || "(none)"} · Gas override: {rules.forceGasMode || "(none)"} · Brain: {rules.brainMode || "(default)"}
            </Text>
          </View>
        ) : (
          <Text style={{ color: theme.colors.textMuted, marginTop: theme.spacing.md }}>Loading rules…</Text>
        )}
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="violet">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Controls</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Every change requires a reason and is appended to an immutable log.
        </Text>

        <View style={{ marginTop: theme.spacing.md, gap: 10 }}>
          {toggles.map((t) => (
            <Pressable
              key={t.title}
              onPress={() => setPending(t)}
              style={{ paddingVertical: 14, paddingHorizontal: 12, borderRadius: theme.radii.lg, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}
            >
              <Text style={{ color: t.tone === "danger" ? theme.colors.danger : theme.colors.text, fontWeight: "900" }}>{t.title}</Text>
              <Text style={{ color: theme.colors.textMuted, marginTop: 4, ...theme.typography.body }}>{t.body}</Text>
            </Pressable>
          ))}
        </View>

        <Pressable
          onPress={() => setExportOpen(true)}
          disabled={!canExport}
          style={{
            marginTop: theme.spacing.lg,
            paddingVertical: 12,
            borderRadius: theme.radii.md,
            backgroundColor: canExport ? theme.colors.cyan : theme.colors.border,
            alignItems: "center",
          }}
        >
          <Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>Export RFT Episodes</Text>
        </Pressable>
        <Text style={{ color: theme.colors.textFaint, marginTop: 8, ...theme.typography.body }}>
          {canExport ? "Creates deterministic replay-driven training episodes without changing execution semantics." : "Connect to backend and unlock operator session to export."}
        </Text>

        <Pressable
          onPress={() => void runExplain()}
          style={{ marginTop: theme.spacing.md, paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface2, alignItems: "center" }}
        >
          <Text style={{ color: theme.colors.text, fontWeight: "900" }}>Explain My Capital</Text>
        </Pressable>

        {status ? <Text style={{ color: theme.colors.textFaint, marginTop: theme.spacing.md }}>{status}</Text> : null}
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Change History</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Immutable log (hash chained). Export via backend audit endpoint.
        </Text>
        <View style={{ marginTop: theme.spacing.md }}>
          {(snap?.governanceHistory ?? []).slice(0, 10).map((e) => (
            <View key={e.id} style={{ paddingVertical: 12, borderTopWidth: 1, borderTopColor: theme.colors.border }}>
              <Text style={{ color: theme.colors.text, fontWeight: "900" }}>{e.action}</Text>
              <Text style={{ color: theme.colors.textMuted, marginTop: 4, ...theme.typography.body }}>Actor: {e.actor} · Reason: {e.reason}</Text>
              <Text style={{ color: theme.colors.textFaint, marginTop: 6, ...theme.typography.mono }}>Hash: {e.hash} · Prev: {e.prevHash}</Text>
            </View>
          ))}
        </View>
      </SurfaceCard>

      <ConfirmReasonDialog
        visible={!!pending}
        title={pending?.title ?? "Confirm"}
        body={pending?.body ?? ""}
        tone={pending?.tone ?? "neutral"}
        requireReason
        onCancel={() => setPending(null)}
        onConfirm={(reason) => pending && applyToggle(pending.patch, reason)}
      />

      <ConfirmReasonDialog
        visible={exportOpen}
        title="Export RFT Episodes"
        body="Exports deterministic replay-backed proposal-only training episodes. Provide a reason for the audit log."
        tone="neutral"
        requireReason
        onCancel={() => setExportOpen(false)}
        onConfirm={(reason) => void doExportEpisodes(reason)}
      />

      <ConfirmDialog
        visible={!!explain}
        title="Explain My Capital"
        body={explain}
        confirmText="Close"
        cancelText="Close"
        onCancel={() => setExplain("")}
        onConfirm={() => setExplain("")}
      />
    </ScrollView>
  );
}
