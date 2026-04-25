import React, { useEffect, useMemo, useState } from "react";
import { View, Text, ScrollView, Pressable } from "react-native";
import { useTheme } from "../../utils/useTheme";
import { pageContentContainerStyle, pageShellStyle } from '../../utils/layout';
import { SurfaceCard } from "../../components/v2/SurfaceCard";
import { TopStatusBar } from "../../components/cc/TopStatusBar";
import { ConfirmReasonDialog } from "../../components/cc/ConfirmReasonDialog";
import { useCommandCenter } from "../../commandCenter/useCommandCenter";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import type { LabStackParamList } from "../../navigation/LabStack";
import type { MutationProposal } from "../../commandCenter/types";
import { useStore } from "../../state/store";
import { metaApply, metaCandidates } from "../../api/client";

export function SandboxLabScreen() {
  const theme = useTheme();
  const cc = useCommandCenter();
  const { state } = useStore();
  const snap = cc.snapshot;
  const [sel, setSel] = useState<MutationProposal | null>(null);
  const [status, setStatus] = useState<string>("");
  const [remote, setRemote] = useState<MutationProposal[]>([]);

  const probation = useMemo(() => {
    if (!snap) return "";
    return `Probation trades left: ${snap.sandbox.probationTradesLeft} · Sandbox NAV $${snap.sandbox.sandboxNavUsd.toFixed(0)}`;
  }, [snap]);

  useEffect(() => {
    let cancelled = false;
    if (cc.source !== "backend") return;
    (async () => {
      try {
        const res = await metaCandidates(state.baseUrl, 12, state.role === "operator" ? state.adminKey : undefined);
        const items = Array.isArray((res as any)?.items) ? (res as any).items : [];
        if (cancelled) return;
        const mapped: MutationProposal[] = items.map((p: any) => ({
          id: String(p.id ?? ""),
          tsMs: Number((p.created_ts ?? 0) * 1000),
          title: String(p.description ?? "Candidate"),
          summary: String(p.reason ?? ""),
          expectedDeltaPct: Number(p.score ?? 0) * 100,
          riskDelta: Number(((p.correlation_penalty ?? 0) - (p.diversity_bonus ?? 0)) * 100),
          probationCapPct: Math.max(0.5, Math.min(10, 2.5 + Number(p?.stress_report?.robustness_score ?? 0) * 4)),
          status: String(p.lifecycle_stage ?? "experimental") === "retired" ? "rejected" : (String(p.lifecycle_stage ?? "experimental") === "paper_trading" || String(p.lifecycle_stage ?? "experimental") === "production") ? "approved" : "queued",
        }));
        setRemote(mapped);
      } catch {
        // keep snapshot proposals if backend fetch fails
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [cc.source, state.baseUrl, state.adminKey, state.role]);

  async function approve(reason: string) {
    if (!sel) return;
    setStatus("Applying proposal…");
    try {
      if (cc.source !== "backend") {
        setStatus(`Approved (demo). Reason logged: ${reason}`);
        return;
      }
      const res = await metaApply(state.baseUrl, sel.id, state.role === "operator" ? state.adminKey : undefined);
      if (!Boolean((res as Record<string, unknown>)?.ok)) {
        setStatus(`Apply failed · ${String((res as Record<string, unknown>)?.error ?? "unknown")}`);
        return;
      }
      setStatus(`Applied ${sel.id}. Lifecycle → ${String((res as Record<string, unknown>)?.lifecycle_stage ?? "paper_trading")}`);
      await cc.refresh();
    } finally {
      setSel(null);
    }
  }

  async function reject(reason: string) {
    if (!sel) return;
    setStatus(`Rejected. Reason: ${reason}`);
    setSel(null);
  }

  const proposals = remote.length ? remote : (snap?.sandbox.proposals ?? []);

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 40)}>
      <TopStatusBar title="Sandbox Lab" subtitle="Experiment safely: probation capital staging" rightTag={probation} live={cc.source === "backend"} />

      <View style={{ height: theme.spacing.md }} />
      <View style={{ flexDirection: "row", gap: 10 }}>
        <Pressable onPress={() => nav.navigate("Tracker")} style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1, alignItems: "center" }}><Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>Replay Tracker</Text></Pressable>
        <Pressable onPress={() => nav.navigate("Agents")} style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.cyan, alignItems: "center" }}><Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>Agents</Text></Pressable>
      </View>

      <View style={{ height: theme.spacing.md }} />
      {snap ? (
        <SurfaceCard glow="cyan">
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Sandbox Isolation</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
            Sandbox is capped and visible everywhere. Mutation proposals must pass robustness + alpha gates before promotion.
          </Text>
          <View style={{ marginTop: theme.spacing.md }}>
            <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>
              Cap: {snap.risk.caps.sandboxCapPct}% NAV · Probation cap: {snap.risk.caps.probationCapPct}% NAV · v1: flashloan atomic only
            </Text>
          </View>
        </SurfaceCard>
      ) : null}

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="violet">
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Mutation Proposals</Text>
          <Pressable onPress={() => void cc.refresh()} style={{ paddingVertical: 6, paddingHorizontal: 10, borderRadius: theme.radii.pill, backgroundColor: theme.colors.surface2 }}>
            <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>Refresh</Text>
          </Pressable>
        </View>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Structural mutations are staged with genealogy, robustness testing, regime tags, and probation caps.
        </Text>

        <View style={{ marginTop: theme.spacing.md }}>
          {proposals.slice(0, 8).map((p) => (
            <Pressable
              key={p.id}
              onPress={() => setSel(p)}
              style={{ paddingVertical: 12, borderTopWidth: 1, borderTopColor: theme.colors.border }}
            >
              <Text style={{ color: theme.colors.text, fontWeight: "900" }}>{p.title}</Text>
              <Text style={{ color: theme.colors.textMuted, marginTop: 4, ...theme.typography.body }}>{p.summary}</Text>
              <Text style={{ color: theme.colors.textFaint, marginTop: 6, ...theme.typography.mono }}>
                Expected Δ {p.expectedDeltaPct.toFixed(1)}% · Risk Δ {p.riskDelta.toFixed(0)} · Probation {p.probationCapPct.toFixed(1)}% NAV
              </Text>
            </Pressable>
          ))}
          {!proposals.length ? <Text style={{ color: theme.colors.textMuted }}>No proposals queued.</Text> : null}
        </View>
        {status ? <Text style={{ color: theme.colors.textFaint, marginTop: theme.spacing.md }}>{status}</Text> : null}
      </SurfaceCard>

      <ConfirmReasonDialog
        visible={!!sel}
        title={sel ? `Approve proposal · ${sel.id}` : "Approve"}
        body={sel ? `${sel.title}\n\n${sel.summary}\n\nProbation cap: ${sel.probationCapPct.toFixed(1)}% NAV` : ""}
        requireReason
        confirmText="Approve"
        cancelText="Reject"
        onCancel={() => {
          if (sel) void reject("operator_reject");
          else setSel(null);
        }}
        onConfirm={approve}
      />
    </ScrollView>
  );
}
