import React from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { useCommandCenter } from "../../commandCenter/useCommandCenter";
import { useTheme } from "../../utils/useTheme";
import { pageContentContainerStyle, pageShellStyle } from "../../utils/layout";
import { BrandHeader } from "../../components/v2/BrandHeader";
import { SurfaceCard } from "../../components/v2/SurfaceCard";

function str(value: unknown): string {
  return value == null ? "" : String(value);
}

function money(value: unknown): string {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(n);
}

export function OpportunitiesScreen() {
  const theme = useTheme();
  const navigation = useNavigation<any>();
  const { snapshot, loading, error, refresh, source } = useCommandCenter();
  const liveItems = Array.isArray(snapshot?.execution?.liveExecution?.items)
    ? snapshot!.execution!.liveExecution!.items!
    : [];

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 20)}>
      <BrandHeader title="Opportunities" subtitle="Canonical opportunity → admission → sizing" rightTag={source === "backend" ? "BACKEND" : "DEMO"} />

      {error ? (
        <SurfaceCard glow="none">
          <Text style={{ color: theme.colors.danger, ...theme.typography.h2 }}>Backend unavailable</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>{error}</Text>
          <Pressable onPress={() => void refresh()} style={{ marginTop: 12, padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border }}>
            <Text style={{ color: theme.colors.cyan, textAlign: "center", fontWeight: "800" }}>Retry</Text>
          </Pressable>
        </SurfaceCard>
      ) : null}

      <SurfaceCard glow="cyan">
        <Text style={{ color: theme.colors.text, ...theme.typography.h2 }}>Market / execution state</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>
          {loading ? "Refreshing canonical snapshot…" : `${snapshot?.observability?.oppsSeen ?? 0} opportunities seen · ${snapshot?.observability?.oppsExecutable ?? 0} executable`}
        </Text>
        <Text style={{ color: snapshot?.globalExecutionBlocked ? theme.colors.danger : theme.colors.good, marginTop: 8, fontWeight: "900" }}>
          {snapshot?.globalExecutionBlocked ? `BLOCKED · ${(snapshot.globalExecutionReasonCodes ?? []).join(", ")}` : "Execution gates open for eligible V1 opportunities"}
        </Text>
      </SurfaceCard>

      {liveItems.length === 0 ? (
        <SurfaceCard glow="none">
          <Text style={{ color: theme.colors.text, ...theme.typography.h2 }}>No live execution items</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>
            The backend has not exposed a live execution item in the current snapshot. No synthetic opportunity is created by the mobile app.
          </Text>
        </SurfaceCard>
      ) : null}

      {liveItems.map((item, index) => {
        const decisionId = str(item.decision_id ?? item.decisionId);
        const family = str(item.family ?? item.strategy_family ?? "flash_arb");
        const provider = str(item.provider ?? item.selectedProvider ?? "—");
        const net = item.net_edge ?? item.realized_net_usd ?? item.expected_net_usd;
        return (
          <Pressable
            key={`${decisionId || "live"}-${index}`}
            onPress={() => decisionId ? navigation.navigate("DecisionDetail", { decisionId }) : undefined}
          >
            <SurfaceCard glow="none">
              <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 12 }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: theme.colors.text, ...theme.typography.h2 }}>{family}</Text>
                  <Text style={{ color: theme.colors.textFaint, marginTop: 4, fontFamily: "monospace" }}>
                    {decisionId || "decision_id unavailable"}
                  </Text>
                </View>
                <Text style={{ color: theme.colors.good, fontWeight: "900" }}>{money(net)}</Text>
              </View>
              <Text style={{ color: theme.colors.textMuted, marginTop: 8 }}>
                Provider: {provider} · Lane: {str(item.lane || "—")} · Route: {str(item.routeFamily || item.route_family || "—")}
              </Text>
              <Text style={{ color: theme.colors.cyan, marginTop: 10, fontWeight: "800" }}>
                {decisionId ? "Open canonical decision →" : "Decision lineage unavailable"}
              </Text>
            </SurfaceCard>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}
