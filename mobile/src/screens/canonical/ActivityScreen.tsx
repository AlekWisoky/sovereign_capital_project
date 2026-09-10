import React, { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { getFundLedger } from "../../contracts/canonicalClient";
import type { FundLedgerProjection, TransactionRecord } from "../../contracts/canonical";
import { useStore } from "../../state/store";
import { useTheme } from "../../utils/useTheme";
import { pageContentContainerStyle, pageShellStyle } from "../../utils/layout";
import { BrandHeader } from "../../components/v2/BrandHeader";
import { SurfaceCard } from "../../components/v2/SurfaceCard";

function text(value: unknown, fallback = "—"): string {
  const out = value == null ? "" : String(value);
  return out || fallback;
}

function money(value: unknown): string {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(n);
}

export function ActivityScreen() {
  const theme = useTheme();
  const navigation = useNavigation<any>();
  const { state } = useStore();
  const [ledger, setLedger] = useState<FundLedgerProjection | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    if (!state.baseUrl) {
      setError("Backend URL is not configured.");
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const result = await getFundLedger(state.baseUrl, { adminKey: state.role === "operator" ? state.adminKey : undefined });
      setLedger(result);
      setError("");
      setUpdatedAt(Date.now());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [state.baseUrl, state.role, state.adminKey]);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 5000);
    return () => clearInterval(timer);
  }, [refresh]);

  const rows: TransactionRecord[] = ledger?.transactions?.length ? ledger.transactions : (ledger?.tail ?? []);

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 20)}>
      <BrandHeader title="Activity" subtitle="Decisions · receipts · settlement · transactions" rightTag="CANONICAL" />

      <SurfaceCard glow="cyan">
        <Text style={{ color: theme.colors.text, ...theme.typography.h2 }}>Transaction history</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>
          {loading ? "Refreshing…" : `${ledger?.transactionCount ?? rows.length} recorded transactions`}
          {updatedAt ? ` · updated ${new Date(updatedAt).toLocaleTimeString()}` : ""}
        </Text>
        {ledger?.balanceSource ? <Text style={{ color: theme.colors.textFaint, marginTop: 5 }}>Source: {ledger.balanceSource}</Text> : null}
      </SurfaceCard>

      {error ? (
        <SurfaceCard glow="none">
          <Text style={{ color: theme.colors.danger, ...theme.typography.h2 }}>History unavailable</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>{error}</Text>
          <Pressable onPress={() => void refresh()} style={{ marginTop: 12, padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border }}>
            <Text style={{ color: theme.colors.cyan, textAlign: "center", fontWeight: "800" }}>Retry</Text>
          </Pressable>
        </SurfaceCard>
      ) : null}

      {rows.map((row, index) => {
        const decisionId = text(row.decisionId, "");
        return (
          <Pressable key={`${row.transactionId ?? row.receiptId ?? row.txHash ?? "tx"}-${index}`} onPress={() => decisionId ? navigation.navigate("DecisionDetail", { decisionId }) : undefined}>
            <SurfaceCard glow="none">
              <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 10 }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: theme.colors.text, ...theme.typography.h2 }}>{text(row.type, "Transaction")}</Text>
                  <Text style={{ color: theme.colors.textFaint, marginTop: 4, fontFamily: "monospace" }}>{text(row.txHash || row.transactionId || row.receiptId)}</Text>
                </View>
                <Text style={{ color: Number(row.realizedNetUsd ?? 0) >= 0 ? theme.colors.good : theme.colors.danger, fontWeight: "900" }}>
                  {money(row.realizedNetUsd)}
                </Text>
              </View>
              <Text style={{ color: theme.colors.textMuted, marginTop: 8 }}>
                {text(row.provider, "Provider unknown")} · {text(row.venue, "Venue unknown")} · {text(row.lane, "Lane unknown")} · {text(row.chain, "Chain unknown")}
              </Text>
              <Text style={{ color: theme.colors.textFaint, marginTop: 5 }}>
                Gas {money(row.gasCostUsd)} · Borrow {money(row.borrowCostUsd)} · Status {text(row.status)}
              </Text>
              {decisionId ? <Text style={{ color: theme.colors.cyan, marginTop: 8, fontFamily: "monospace" }}>decision_id {decisionId}</Text> : null}
            </SurfaceCard>
          </Pressable>
        );
      })}

      {!loading && rows.length === 0 && !error ? (
        <SurfaceCard glow="none">
          <Text style={{ color: theme.colors.text, ...theme.typography.h2 }}>No transactions recorded</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>The mobile app will not fabricate trade history. It will display only backend ledger/receipt evidence.</Text>
        </SurfaceCard>
      ) : null}
    </ScrollView>
  );
}
