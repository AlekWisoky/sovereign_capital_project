import React, { useMemo, useState } from "react";
import { View, Text, ScrollView, Pressable } from "react-native";
import { useTheme } from "../../utils/useTheme";
import { pageContentContainerStyle, pageShellStyle } from '../../utils/layout';
import { SurfaceCard } from "../../components/v2/SurfaceCard";
import { TopStatusBar } from "../../components/cc/TopStatusBar";
import { MultiLineChart } from "../../components/cc/charts/MultiLineChart";
import { useCommandCenter } from "../../commandCenter/useCommandCenter";
import { ConfirmDialog } from "../../components/v2/ConfirmDialog";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import type { AIStackParamList } from "../../navigation/AIStack";

export function MindOfMachineScreen() {
  const theme = useTheme();
  const cc = useCommandCenter();
  const snap = cc.snapshot;
  const [sel, setSel] = useState<string | null>(null);
  const nav = useNavigation<NativeStackNavigationProp<AIStackParamList>>();
  const item = useMemo(() => snap?.decisions.find((d) => d.id === sel) ?? null, [snap, sel]);

  const rewardTraceText = useMemo(() => {
    if (!item?.rewardTrace) return "(no reward trace)";
    try {
      const r: any = item.rewardTrace;
      const ppm = typeof r.reward_scaled_ppm === "number" ? r.reward_scaled_ppm : Number(r.reward_scaled_ppm ?? 0);
      return `reward_scaled_ppm: ${ppm}\namount_in_wei: ${r.amount_in_wei ?? ""}\nexpected_after_costs_wei: ${r.expected_after_costs_wei ?? ""}\nrealized_after_gas_wei: ${r.realized_after_gas_wei ?? ""}\nsubmit_to_receipt_ms: ${r.submit_to_receipt_ms ?? ""}`;
    } catch {
      return "(invalid reward trace)";
    }
  }, [item]);

  const series = useMemo(() => {
    const decisions = (snap?.decisions ?? []).slice(0, 30).reverse();
    const conf = decisions.map((d) => d.confidence);
    const reality = decisions.map((d) => {
      // Map outcome to a comparable 0..1 scale.
      if (d.outcome === "success") return 0.85 + 0.15 * (d.reward ?? 0);
      if (d.outcome === "skipped") return 0.55;
      if (d.outcome === "fail") return 0.15;
      return 0.5;
    });
    return { conf, reality };
  }, [snap]);

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 40)}>
      <TopStatusBar title="AI Assistant" subtitle="Explain → Suggest → Auto · decision audit logs · reward trace" rightTag={cc.source === "backend" ? "BACKEND" : "DEMO"} live={cc.source === "backend"} />

      <View style={{ height: theme.spacing.md }} />
      <View style={{ flexDirection: "row", gap: 10 }}>
        <Pressable onPress={() => nav.navigate("Agents")} style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1, alignItems: "center" }}><Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>Agents</Text></Pressable>
        <Pressable onPress={() => nav.navigate("Tracker")} style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.cyan, alignItems: "center" }}><Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>Tracker</Text></Pressable>
      </View>

      <View style={{ height: theme.spacing.md }} />
      {snap ? (
        <SurfaceCard glow="cyan">
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Assistant Overview</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
            Current regime: <Text style={{ color: theme.colors.cyan, fontWeight: "900" }}>{snap.regime.current}</Text> · Confidence {Math.round(snap.regime.confidence * 100)}%
          </Text>

          <View style={{ marginTop: theme.spacing.md }}>
            {snap.regime.history.slice(0, 6).map((h, i) => (
              <Text key={i} style={{ color: theme.colors.textFaint, ...theme.typography.mono, marginTop: i ? 6 : 0 }}>
                {new Date(h.tsMs).toISOString().slice(11, 19)} · {h.regime}
              </Text>
            ))}
          </View>
        </SurfaceCard>
      ) : null}

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="violet">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Confidence vs Reality</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Cyan = AI confidence · Violet = realized outcome proxy. Goal: tight tracking under live walk-forward.
        </Text>
        <View style={{ marginTop: theme.spacing.md }}>
          <MultiLineChart a={series.conf} b={series.reality} height={140} />
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Decision Flow Map</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Sovereign boundary: AI proposes → Capital validates → Execution executes → Receipt settles → Reward updates.
        </Text>
        <View style={{ marginTop: theme.spacing.md, flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
          {[
            { t: "AI\nProposal", c: theme.colors.surface2 },
            { t: "Capital\nGate", c: theme.colors.surface2 },
            { t: "Execute\nTx", c: theme.colors.surface2 },
            { t: "Receipt\nOutcome", c: theme.colors.surface2 },
            { t: "RL\nReward Trace", c: theme.colors.surface2 },
          ].map((b, i) => (
            <View
              key={i}
              style={{
                paddingVertical: 10,
                paddingHorizontal: 12,
                borderRadius: theme.radii.md,
                borderWidth: 1,
                borderColor: theme.colors.border,
                backgroundColor: b.c,
                minWidth: 120,
              }}
            >
              <Text style={{ color: theme.colors.text, fontWeight: "900" }}>{b.t}</Text>
            </View>
          ))}
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="none">
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Decision Log</Text>
          <Pressable onPress={() => void cc.refresh()} style={{ paddingVertical: 6, paddingHorizontal: 10, borderRadius: theme.radii.pill, backgroundColor: theme.colors.surface2 }}>
            <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>Refresh</Text>
          </Pressable>
        </View>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Commit-like entries. Tap for “why”, outcome, and reward trace.
        </Text>

        <View style={{ marginTop: theme.spacing.md }}>
          {(snap?.decisions ?? []).slice(0, 24).map((d) => {
            const tone = d.outcome === "success" ? theme.colors.good : d.outcome === "fail" ? theme.colors.danger : theme.colors.textFaint;
            return (
              <Pressable
                key={d.id}
                onPress={() => setSel(d.id)}
                style={{
                  paddingVertical: 12,
                  borderTopWidth: 1,
                  borderTopColor: theme.colors.border,
                }}
              >
                <Text style={{ color: tone, fontWeight: "900" }}>{d.intent}</Text>
                <Text style={{ color: theme.colors.textMuted, marginTop: 4, ...theme.typography.body }}>
                  Confidence {Math.round(d.confidence * 100)}% · {d.strategies.join(", ")}
                </Text>
                <Text style={{ color: theme.colors.textFaint, marginTop: 6, ...theme.typography.mono }}>
                  Outcome: {(d.outcome ?? "unknown").toUpperCase()} · Reward: {(d.reward ?? 0).toFixed(2)}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </SurfaceCard>

      <ConfirmDialog
        visible={!!item}
        title={item ? `Decision · ${item.id}` : "Decision"}
        body={
          item
            ? `Intent: ${item.intent}\n\nStrategies: ${item.strategies.join(", ")}\n\nConfidence: ${Math.round(item.confidence * 100)}%\nOutcome: ${item.outcome ?? "unknown"}\nReward: ${(item.reward ?? 0).toFixed(4)}\n\nReward trace:\n${rewardTraceText}\n\nNotes: ${item.notes ?? "(none)"}`
            : ""
        }
        onCancel={() => setSel(null)}
        onConfirm={() => setSel(null)}
        confirmText="Close"
        cancelText="Close"
      />
    </ScrollView>
  );
}
