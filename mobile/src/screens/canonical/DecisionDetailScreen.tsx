import React, { useCallback, useEffect, useState } from "react";
import { ScrollView, Text } from "react-native";
import { RouteProp, useRoute } from "@react-navigation/native";
import { getDecisionDetail } from "../../contracts/canonicalClient";
import type { DecisionDetail } from "../../contracts/canonical";
import { useStore } from "../../state/store";
import { useTheme } from "../../utils/useTheme";
import { pageContentContainerStyle, pageShellStyle } from "../../utils/layout";
import { BrandHeader } from "../../components/v2/BrandHeader";
import { SurfaceCard } from "../../components/v2/SurfaceCard";

function money(value: unknown): string {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(n) : "—";
}

function line(label: string, value: unknown, color: string) {
  return <Text style={{ color, marginTop: 7 }}><Text style={{ fontWeight: "800" }}>{label}: </Text>{value == null || value === "" ? "—" : String(value)}</Text>;
}

export function DecisionDetailScreen() {
  const theme = useTheme();
  const { state } = useStore();
  const route = useRoute<RouteProp<{ DecisionDetail: { decisionId: string } }, "DecisionDetail">>();
  const decisionId = String(route.params?.decisionId || "");
  const [detail, setDetail] = useState<DecisionDetail | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!decisionId || !state.baseUrl) {
      setError("Missing decision identity or backend URL.");
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      setDetail(await getDecisionDetail(state.baseUrl, decisionId, { adminKey: state.role === "operator" ? state.adminKey : undefined }));
      setError("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [decisionId, state.baseUrl, state.role, state.adminKey]);

  useEffect(() => { void refresh(); }, [refresh]);

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 20)}>
      <BrandHeader title="Decision Detail" subtitle="Canonical lifecycle lineage" rightTag="DECISION" />

      <SurfaceCard glow="cyan">
        <Text style={{ color: theme.colors.text, ...theme.typography.h2 }}>decision_id</Text>
        <Text style={{ color: theme.colors.cyan, marginTop: 8, fontFamily: "monospace" }}>{decisionId || "—"}</Text>
        {loading ? <Text style={{ color: theme.colors.textMuted, marginTop: 8 }}>Loading canonical decision…</Text> : null}
        {error ? <Text style={{ color: theme.colors.danger, marginTop: 8 }}>{error}</Text> : null}
      </SurfaceCard>

      {detail ? (
        <>
          <SurfaceCard glow="none">
            <Text style={{ color: theme.colors.text, ...theme.typography.h2 }}>Decision → admission</Text>
            {line("Opportunity", detail.opportunityId, theme.colors.textMuted)}
            {line("Family", detail.strategyFamily, theme.colors.textMuted)}
            {line("Expected net", money(detail.expectedNetUsd), theme.colors.textMuted)}
            {line("Admission", detail.admission?.status ?? (detail.admission?.allowed ? "allowed" : "blocked"), detail.admission?.allowed ? theme.colors.good : theme.colors.danger)}
            {line("Admission reasons", (detail.admission?.reasonCodes ?? []).join(", "), theme.colors.textFaint)}
          </SurfaceCard>

          <SurfaceCard glow="none">
            <Text style={{ color: theme.colors.text, ...theme.typography.h2 }}>Sizing → execution</Text>
            {line("Size multiplier", detail.sizing?.sizeMult, theme.colors.textMuted)}
            {line("Borrow multiplier", detail.sizing?.borrowMult, theme.colors.textMuted)}
            {line("Amount USD", money(detail.sizing?.amountInUsd), theme.colors.textMuted)}
            {line("Amount raw", detail.sizing?.amountInRaw, theme.colors.textFaint)}
            {line("Provider", detail.sizing?.provider, theme.colors.textMuted)}
            {line("Execution lane", detail.execution?.lane, theme.colors.textMuted)}
            {line("Send mode", detail.execution?.sendMode, theme.colors.textMuted)}
            {line("Transaction", detail.execution?.txHash, theme.colors.textFaint)}
          </SurfaceCard>

          <SurfaceCard glow="none">
            <Text style={{ color: theme.colors.text, ...theme.typography.h2 }}>Receipt → settlement</Text>
            {line("Receipt", detail.receipt?.txHash ?? detail.receiptId, theme.colors.textMuted)}
            {line("Provider", detail.receipt?.provider, theme.colors.textMuted)}
            {line("Settlement verified", detail.settlement?.verified ? "YES" : "NO", detail.settlement?.verified ? theme.colors.good : theme.colors.danger)}
            {line("Realized after gas", money(detail.settlement?.realizedAfterGasUsd), theme.colors.textMuted)}
            {line("Gas", money(detail.settlement?.gasCostUsd), theme.colors.textMuted)}
            {line("Borrow cost", money(detail.settlement?.borrowCostUsd), theme.colors.textMuted)}
            {line("Realized net", money(detail.realizedNetUsd ?? detail.settlement?.netRealizedUsd), theme.colors.textMuted)}
          </SurfaceCard>

          <SurfaceCard glow="none">
            <Text style={{ color: theme.colors.text, ...theme.typography.h2 }}>Expectation → learning</Text>
            {line("Expectation error", money(detail.expectationErrorUsd ?? detail.learning?.expectationErrorUsd), theme.colors.textMuted)}
            {line("Learning recorded", detail.learning?.learned ? "YES" : "NO", detail.learning?.learned ? theme.colors.good : theme.colors.textMuted)}
            {line("Outcome ID", detail.outcomeId, theme.colors.textFaint)}
            {line("Learning attribution", detail.learning?.attribution ? "Canonical settlement attribution" : "—", theme.colors.textFaint)}
          </SurfaceCard>
        </>
      ) : null}
    </ScrollView>
  );
}
