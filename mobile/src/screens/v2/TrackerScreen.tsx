import React, { useEffect, useMemo, useState } from "react";
import { View, Text, ScrollView, Pressable, TextInput } from "react-native";
import { useStore } from "../../state/store";
import { useTickets } from "../../state/ticketsContext";
import { newTicket, type TradeTicket } from "../../state/tickets";
import { useTheme } from "../../utils/useTheme";
import { pageContentContainerStyle, pageShellStyle } from '../../utils/layout';
import { BrandHeader } from "../../components/v2/BrandHeader";
import { SurfaceCard } from "../../components/v2/SurfaceCard";
import { CompactTable } from "../../components/v2/CompactTable";
import { ConfirmDialog } from "../../components/v2/ConfirmDialog";
import { TicketStepper } from "../../components/v2/TicketStepper";
import { RouteGraph } from "../../components/v2/RouteGraph";
import { Sparkline } from "../../components/v2/charts/Sparkline";
import { fmtCompact } from "../../utils/format";
import type { Opportunity } from "../../utils/types";
import type { JsonValue } from "../../utils/types";
import { fetchState, simulateOpportunity, tradeOpportunity, txReceipt } from "../../api/client";
import { VictorSummaryWS, type WsMessage } from "../../api/wsSummary";

function asRecord(v: unknown): Record<string, unknown> | null {
  return typeof v === "object" && v !== null ? (v as Record<string, unknown>) : null;
}

function num(v: unknown, fallback: number = 0): number {
  const n = typeof v === "number" ? v : typeof v === "string" ? Number(v) : NaN;
  return Number.isFinite(n) ? n : fallback;
}

export function TrackerScreen() {
  const theme = useTheme();
  const { state, session, setSession, multichain } = useStore();
  const { tickets, upsert, patch } = useTickets();
  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [selectedOppId, setSelectedOppId] = useState<string>("");
  const [amountOverride, setAmountOverride] = useState<string>("");
  const [activeTicket, setActiveTicket] = useState<TradeTicket | null>(null);
  const [confirmExec, setConfirmExec] = useState(false);
  const [routeOpen, setRouteOpen] = useState(false);
  const [status, setStatus] = useState<string>("");
  const [scanHist, setScanHist] = useState<number[]>([]);

  const selectedOpp = useMemo(() => opps.find((o) => o.id === selectedOppId) ?? null, [opps, selectedOppId]);

  const operator = state.role === "operator" && !session.locked;

  useEffect(() => {
    let stop = false;
    const loop = async () => {
      while (!stop) {
        try {
          const st = await fetchState(state.baseUrl, state.role === "operator" ? state.adminKey : undefined);
          if (stop) break;
          setOpps(st.opportunities || []);
        } catch {
          // ignore
        }
        await new Promise((r) => setTimeout(r, 2200));
      }
    };
    void loop();
    return () => {
      stop = true;
    };
  }, [state.baseUrl, state.role, state.adminKey]);

  useEffect(() => {
    const ws = new VictorSummaryWS();
    const onMsg = (msg: WsMessage) => {
      const scanMs = typeof msg.data?.scan_ms === "number" ? msg.data.scan_ms : undefined;
      if (scanMs === undefined) return;
      setScanHist((h) => [...h, scanMs].slice(-42));
    };
    ws.on(onMsg);
    ws.open(state.baseUrl);
    return () => ws.close();
  }, [state.baseUrl]);

  async function selectOpp(id: string) {
    setSelectedOppId(id);
    const opp = opps.find((o) => o.id === id);
    if (!opp) return;
    const t = newTicket(opp, {
      chain: multichain.active || opp.chain,
      amountInOverride: amountOverride.trim() || undefined,
      sendMode: String(state.sendMode || ""),
      gasMode: String(state.gasMode || ""),
      brainMode: String(state.brainMode || ""),
    });
    await upsert(t);
    setActiveTicket(t);
    setStatus("Ticket created.");
  }

  async function runSimulate() {
    if (!selectedOpp) return;
    if (state.role !== "operator" || session.locked) {
      setStatus("Read-only: simulate is disabled (requires operator key).");
      return;
    }
    const t = activeTicket ?? newTicket(selectedOpp, { chain: selectedOpp.chain });
    await upsert(t);
    setActiveTicket(t);
    setStatus("Simulating…");
    try {
      const res = await simulateOpportunity(state.baseUrl, selectedOpp.id, state.adminKey, amountOverride.trim() || undefined);
      await patch(t.id, { stage: "SIMULATED", simulate: res, amountInOverride: amountOverride.trim() || undefined });
      setStatus("Simulated.");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      await patch(t.id, { stage: "FAILED" });
      setStatus(`Simulate failed · ${msg}`);
    }
  }

  async function runExecute() {
    if (!selectedOpp || !activeTicket) return;
    if (!operator) {
      setStatus("Locked/Read-only: unlock + ARM to execute.");
      return;
    }
    if (!session.armed) {
      setStatus("Not ARMED.");
      return;
    }
    setConfirmExec(false);
    setStatus("Executing…");
    try {
      const res = await tradeOpportunity(state.baseUrl, selectedOpp.id, state.adminKey, amountOverride.trim() || undefined);
      const txHash = typeof res.tx_hash === "string" ? res.tx_hash : "";
      await patch(activeTicket.id, { stage: "EXEC_SENT", trade: res });
      setStatus(txHash ? `Sent · ${txHash}` : "Sent");

      if (!txHash) return;
      // Poll receipt decode.
      const start = Date.now();
      let decodedOnce = false;
      while (Date.now() - start < 75_000) {
        try {
          const rr = await txReceipt(state.baseUrl, txHash, state.adminKey);
          const receipt = asRecord(rr)?.["receipt"];
          const decoded = asRecord(rr)?.["decoded"];
          if (receipt) {
            await patch(activeTicket.id, { stage: "MINED", receipt: receipt as JsonValue });
          }
          if (decoded) {
            decodedOnce = true;
            await patch(activeTicket.id, { stage: "DECODED", decoded: decoded as JsonValue });
            setStatus("Decoded.");
            break;
          }
        } catch {
          // ignore
        }
        await new Promise((r) => setTimeout(r, 2400));
      }
      if (!decodedOnce) setStatus("Receipt polling timed out.");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      await patch(activeTicket.id, { stage: "FAILED" });
      setStatus(`Execute failed · ${msg}`);
    }
  }

  const topRows = useMemo(() => {
    const rows = [...opps]
      .sort((a, b) => Number(b.expected_profit_wei) - Number(a.expected_profit_wei))
      .slice(0, 8)
      .map((o) => {
        const ev = num(o.expected_profit_wei, 0) / 1e18;
        const diff = num(o.profit_after_gas_estimate_wei, 0) / 1e18;
        const tone = diff > 0 ? "good" : o.can_execute ? "warn" : "neutral";
        return {
          key: o.id,
          cols: [String(o.strategy), fmtCompact(diff), fmtCompact(ev), o.can_execute ? "READY" : "LOCK"],
          tone,
        };
      });
    return rows;
  }, [opps]);

  const activeStage = useMemo(() => {
    const t = activeTicket ? tickets.find((x) => x.id === activeTicket.id) : null;
    return t?.stage ?? (activeTicket?.stage ?? "NEW");
  }, [tickets, activeTicket]);

  const receiptTimes = useMemo(() => {
    const out: number[] = [];
    for (const t of tickets.slice(0, 40)) {
      const decodedAt = t.timeline?.decodedAt;
      if (typeof decodedAt === "number") out.push((decodedAt - t.createdAt) / 1000);
    }
    return out.reverse();
  }, [tickets]);

  const rightTag = `${state.role === "operator" ? (session.locked ? "LOCKED" : session.armed ? "ARMED" : "SAFE") : "READ"} · ${(multichain.active || state.chain).toUpperCase()}`;

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 24)}>
      <BrandHeader title="Tracker" subtitle="Trade tickets + execution" rightTag={rightTag} />

      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Top Opportunities</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>Tap to create a ticket.</Text>
        <View style={{ marginTop: theme.spacing.md }}>
          <CompactTable header={["pair", "diff", "EV", "state"]} rows={topRows} onPressRow={(id) => void selectOpp(id)} />
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />

      <SurfaceCard glow="cyan">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Ticket Builder</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Opportunity → Simulate → Preflight → Execute → Receipt Decode → PnL Attribution
        </Text>

        <View style={{ marginTop: theme.spacing.md }}>
          <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Selected</Text>
          <Text style={{ color: theme.colors.text, marginTop: 4, fontFamily: "monospace" }}>{selectedOpp ? `${selectedOpp.strategy} · ${selectedOpp.id}` : "(none)"}</Text>
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>amount_in_override (optional)</Text>
          <TextInput
            value={amountOverride}
            onChangeText={setAmountOverride}
            placeholder="wei"
            placeholderTextColor={theme.colors.textFaint}
            keyboardType="numeric"
            style={{
              marginTop: 8,
              padding: 12,
              borderRadius: theme.radii.md,
              borderWidth: 1,
              borderColor: theme.colors.border,
              color: theme.colors.text,
              backgroundColor: theme.colors.surface1,
              fontFamily: "monospace",
            }}
          />
        </View>

        {activeTicket ? <TicketStepper stage={activeStage} /> : null}

        <View style={{ flexDirection: "row", gap: 10, marginTop: theme.spacing.lg }}>
          <Pressable
            onPress={() => setSession({ armed: !session.armed })}
            disabled={state.role !== "operator" || session.locked}
            style={{
              flex: 1,
              paddingVertical: 12,
              borderRadius: theme.radii.md,
              borderWidth: 1,
              borderColor: session.armed ? theme.colors.good : theme.colors.border,
              backgroundColor: session.armed ? theme.colors.surface2 : theme.colors.surface1,
              alignItems: "center",
              opacity: state.role === "operator" && !session.locked ? 1 : 0.5,
            }}
          >
            <Text style={{ color: session.armed ? theme.colors.good : theme.colors.textMuted, fontWeight: "900" }}>{session.armed ? "ARMED" : "ARM"}</Text>
          </Pressable>

          <Pressable
            onPress={() => void runSimulate()}
            disabled={!selectedOpp || state.role !== "operator" || session.locked}
            style={{
              flex: 1,
              paddingVertical: 12,
              borderRadius: theme.radii.md,
              backgroundColor: theme.colors.violet,
              alignItems: "center",
              opacity: selectedOpp && state.role === "operator" && !session.locked ? 1 : 0.5,
            }}
          >
            <Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>Simulate</Text>
          </Pressable>
        </View>

        <View style={{ flexDirection: "row", gap: 10, marginTop: 10 }}>
          <Pressable
            onPress={() => setRouteOpen((v) => !v)}
            disabled={!selectedOpp}
            style={{
              flex: 1,
              paddingVertical: 12,
              borderRadius: theme.radii.md,
              borderWidth: 1,
              borderColor: theme.colors.border,
              backgroundColor: theme.colors.surface1,
              alignItems: "center",
              opacity: selectedOpp ? 1 : 0.5,
            }}
          >
            <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>{routeOpen ? "Hide" : "Route"}</Text>
          </Pressable>

          <Pressable
            onPress={() => setConfirmExec(true)}
            disabled={!selectedOpp || !activeTicket || !operator || !session.armed}
            style={{
              flex: 1,
              paddingVertical: 12,
              borderRadius: theme.radii.md,
              backgroundColor: theme.colors.cyan,
              alignItems: "center",
              opacity: selectedOpp && activeTicket && operator && session.armed ? 1 : 0.5,
            }}
          >
            <Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>Execute</Text>
          </Pressable>
        </View>

        {routeOpen && selectedOpp ? (
          <View style={{ marginTop: theme.spacing.md }}>
            <Text style={{ color: theme.colors.textMuted, ...theme.typography.mono }}>Route Inspector</Text>
            <RouteGraph width={330} height={90} path={selectedOpp.path} legs={selectedOpp.legs} />
          </View>
        ) : null}

        {status ? <Text style={{ color: theme.colors.textMuted, marginTop: theme.spacing.md, ...theme.typography.mono }}>{status}</Text> : null}
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />

      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Latency & Fill</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>scan_ms (ws) and receipt decode time (local tickets)</Text>

        <View style={{ marginTop: theme.spacing.md }}>
          <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>scan_ms</Text>
          <Sparkline width={330} height={44} data={scanHist.length ? scanHist : [900, 820, 760, 980, 700]} tone="neutral" />
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>receipt_time_s</Text>
          <Sparkline width={330} height={44} data={receiptTimes.length ? receiptTimes : [12, 9, 15, 8, 11]} tone={receiptTimes.length ? "good" : "neutral"} />
        </View>
      </SurfaceCard>

      <ConfirmDialog
        visible={confirmExec}
        title="Execute trade?"
        body={
          selectedOpp
            ? `This will send a transaction for ${selectedOpp.strategy}.\n\nNo hold-to-execute: confirmation is tap-based.\n\nEnsure settings and chain are correct.`
            : ""
        }
        confirmText="Send"
        cancelText="Cancel"
        onCancel={() => setConfirmExec(false)}
        onConfirm={() => void runExecute()}
      />
    </ScrollView>
  );
}
