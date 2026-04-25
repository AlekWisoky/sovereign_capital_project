import React, { useEffect, useMemo, useRef, useState } from "react";
import { View, Text, ScrollView, Pressable } from "react-native";
import { useStore } from "../../state/store";
import { useTheme } from "../../utils/useTheme";
import { pageContentContainerStyle, pageShellStyle } from '../../utils/layout';
import { BrandHeader } from "../../components/v2/BrandHeader";
import { StatTile } from "../../components/v2/StatTile";
import { SurfaceCard } from "../../components/v2/SurfaceCard";
import { SegmentedTabs } from "../../components/v2/SegmentedTabs";
import { AreaChart } from "../../components/v2/charts/AreaChart";
import { Histogram } from "../../components/v2/charts/Histogram";
import { fmtCompact, fmtMs, fmtPct } from "../../utils/format";
import { VictorSummaryWS, type SummaryData, type WsMessage } from "../../api/wsSummary";
import { adminState, pnlSummary, pnlIncome, setSettings } from "../../api/client";

type RangeKey = "1H" | "24H" | "7D" | "30D" | "ALL";

function rangeToWindow(r: RangeKey): number {
  // pnl.summary is trade-window based, so we approximate by a trade count.
  if (r === "1H") return 30;
  if (r === "24H") return 120;
  if (r === "7D") return 600;
  if (r === "30D") return 2000;
  return 5000;
}

function buildHistogram(values: readonly number[], bins: number = 18): number[] {
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const out = new Array(bins).fill(0);
  for (const v of values) {
    const t = (v - min) / range;
    const idx = Math.max(0, Math.min(bins - 1, Math.floor(t * bins)));
    out[idx] += 1;
  }
  return out;
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return typeof v === "object" && v !== null ? (v as Record<string, unknown>) : null;
}

function asArray(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

function num(v: unknown, fallback: number = 0): number {
  const n = typeof v === "number" ? v : typeof v === "string" ? Number(v) : NaN;
  return Number.isFinite(n) ? n : fallback;
}

export function DashScreen() {
  const theme = useTheme();
  const { state, session, multichain, refreshMultichain, selectActiveChain } = useStore();
  const [range, setRange] = useState<RangeKey>("24H");
  const [summary, setSummary] = useState<SummaryData>({});
  const [adminSnap, setAdminSnap] = useState<Record<string, unknown>>({});
  const [pnlCurve, setPnlCurve] = useState<number[]>([]);
  const [evBins, setEvBins] = useState<number[]>([]);
  const [income, setIncome] = useState<Record<string, unknown>>({});

  const wsRef = useRef<VictorSummaryWS | null>(null);

  const operatorControlsEnabled = state.role === "operator" && !session.locked;

  useEffect(() => {
    const ws = new VictorSummaryWS();
    wsRef.current = ws;
    const onMsg = (msg: WsMessage) => {
      if (msg.type === "summary") setSummary(msg.data);
      if (msg.type === "delta") setSummary((s) => ({ ...s, ...(msg.data || {}) }));
    };
    ws.on(onMsg);
    ws.open(state.baseUrl);
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [state.baseUrl]);

  useEffect(() => {
    // Poll admin snapshot and pnl summary (kept lightweight).
    let stop = false;
    const loop = async () => {
      while (!stop) {
        try {
          const a = await adminState(state.baseUrl, state.role === "operator" ? state.adminKey : undefined);
          if (!stop) setAdminSnap(a as Record<string, unknown>);
        } catch {
          // ignore
        }
        try {
          const p = await pnlSummary(state.baseUrl, rangeToWindow(range), state.role === "operator" ? state.adminKey : undefined);
          const rows = (asRecord(p)?.["recent_trades"] as unknown) ?? null;
          if (Array.isArray(rows)) {
            const points: number[] = [];
            let acc = 0;
            const evVals: number[] = [];
            for (const r of rows) {
              const obj = (typeof r === "object" && r !== null ? (r as Record<string, unknown>) : null);
              if (!obj) continue;
              const rp = num(obj["realized_profit_after_gas_wei"], 0);
              acc += rp / 1e18;
              points.push(acc);
              const ev = num(obj["expected_profit_after_costs_wei"], 0);
              evVals.push(ev / 1e18);
            }
            if (!stop) {
              setPnlCurve(points.reverse());
              setEvBins(buildHistogram(evVals));
            }
          }
        } catch {
          // ignore
        }
        try {
          const inc = await pnlIncome(state.baseUrl, state.role === "operator" ? state.adminKey : undefined);
          if (!stop) setIncome(inc as Record<string, unknown>);
        } catch {
          // ignore
        }
        await new Promise((r) => setTimeout(r, 3500));
      }
    };
    void loop();
    return () => {
      stop = true;
    };
  }, [state.baseUrl, state.role, state.adminKey, range]);

  useEffect(() => {
    void refreshMultichain();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.baseUrl]);

  const settings = (adminSnap["settings"] as Record<string, unknown> | undefined) ?? {};
  const bankroll = (adminSnap["bankroll"] as Record<string, unknown> | undefined) ?? {};
  const cb = (adminSnap["circuit_breaker"] as Record<string, unknown> | undefined) ?? {};
  const rpc = (adminSnap["rpc"] as Record<string, unknown> | undefined) ?? {};

  const scanMs = Number(summary.scan_ms ?? 0);
  const successRate = num(summary.metrics?.success_rate_pct, num(asRecord(asRecord(bankroll)?.["state"])?.["success_rate_pct"], 0));
  const efficiency = num(summary.metrics?.efficiency_pct, num(asRecord(adminSnap["efficiency"])?.["efficiency_pct"], 0));
  const oppCount = Number(summary.opp_count ?? 0);
  const balanceWei = num(asRecord(asRecord(bankroll)?.["state"])?.["realized_profit_wei"], 0);

  const rpcOkPct = useMemo(() => {
    const reads = asArray(asRecord(rpc)?.["read"]);
    const sends = asArray(asRecord(rpc)?.["send"]);
    const all = [...reads, ...sends].map(asRecord).filter((x): x is Record<string, unknown> => Boolean(x));
    if (!all.length) return 0;
    const ok = all.filter((x) => Boolean(x["ok"])).length;
    return (ok / all.length) * 100;
  }, [rpc]);

  const circuitOpen = Boolean(asRecord(cb)?.["open"]);
  const kellyEnabled = Boolean(settings["kelly_enabled"]);
  const brainMode = String(settings["brain_mode"] ?? "off");

  async function patchSettings(patch: Record<string, unknown>) {
    if (!operatorControlsEnabled) return;
    try {
      await setSettings(state.baseUrl, patch, state.adminKey);
    } catch {
      // ignore
    }
  }

  const chainLabel = multichain.active || state.chain;
  const rightTag = `${state.role === "operator" ? (session.locked ? "LOCKED" : "OPERATOR") : "READ"} · ${chainLabel.toUpperCase()}`;

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 24)}>
      <BrandHeader title="Dash" subtitle="QuickSight-style analytics" rightTag={rightTag} />

      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: theme.spacing.sm }}>
        <StatTile label="Balance" value={fmtCompact(balanceWei / 1e18)} hint="ETH" tone="neutral" />
        <StatTile label="Opportunities" value={String(oppCount)} hint="live" tone={oppCount > 0 ? "good" : "neutral"} />
        <StatTile label="Efficiency" value={fmtPct(efficiency, 1)} hint="risk-adj" tone={efficiency > 0 ? "good" : "neutral"} />
        <StatTile label="Success" value={fmtPct(successRate, 1)} hint="bankroll" tone={successRate > 55 ? "good" : successRate > 35 ? "warn" : "danger"} />
        <StatTile label="Scan" value={fmtMs(scanMs)} hint="latency" tone={scanMs > 0 && scanMs < 650 ? "good" : scanMs > 1200 ? "warn" : "neutral"} />
        <StatTile label="RPC health" value={fmtPct(rpcOkPct, 0)} hint="read+send" tone={rpcOkPct > 90 ? "good" : rpcOkPct > 70 ? "warn" : "danger"} />
        <StatTile label="Circuit" value={circuitOpen ? "OPEN" : "CLOSED"} hint={circuitOpen ? "blocked" : "ok"} tone={circuitOpen ? "danger" : "good"} />
      </View>

      <View style={{ height: theme.spacing.lg }} />

      <SurfaceCard glow="none">
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: theme.spacing.md }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>PnL Curve</Text>
          <View style={{ width: 220 }}>
            <SegmentedTabs options={["1H", "24H", "7D", "30D", "ALL"] as const} value={range} onChange={setRange} />
          </View>
        </View>
        <AreaChart width={330} height={140} data={pnlCurve.length ? pnlCurve : [0, 0.2, 0.15, 0.3]} />
        <Text style={{ color: theme.colors.textFaint, marginTop: 8, ...theme.typography.mono }}>cumulative realized profit (approx ETH)</Text>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />

      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>EV Distribution</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>Histogram of expected profit-after-costs (approx ETH)</Text>
        <View style={{ marginTop: theme.spacing.md }}>
          <Histogram width={330} height={110} bins={evBins.length ? evBins : [1, 3, 6, 4, 2, 1]} />
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />

      <SurfaceCard glow="violet">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Income Streams</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Live attribution from /api/pnl/income (fees, arb, MEV, funding, yield).
        </Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: theme.spacing.md, fontFamily: "monospace" }}>
          {JSON.stringify(income, null, 2)}
        </Text>
      </SurfaceCard>

      <View style={{ height: theme.spacing.lg }} />

      <SurfaceCard glow="cyan">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Quick Controls</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Operator-only controls (read-only mode disables mutating endpoints).
        </Text>

        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: theme.spacing.md }}>
          <Pressable
            disabled={!operatorControlsEnabled}
            onPress={() => patchSettings({ auto_trading: !Boolean(settings["auto_trading"]) })}
            style={{
              flexBasis: "48%",
              paddingVertical: 12,
              borderRadius: theme.radii.md,
              backgroundColor: operatorControlsEnabled ? theme.colors.surface2 : theme.colors.surface1,
              borderWidth: 1,
              borderColor: operatorControlsEnabled ? theme.colors.cyan : theme.colors.border,
              alignItems: "center",
            }}
          >
            <Text style={{ color: theme.colors.text, fontWeight: "900" }}>auto_trading: {String(Boolean(settings["auto_trading"]))}</Text>
          </Pressable>

          <Pressable
            disabled={!operatorControlsEnabled}
            onPress={() => patchSettings({ dry_run: !Boolean(settings["dry_run"]) })}
            style={{
              flexBasis: "48%",
              paddingVertical: 12,
              borderRadius: theme.radii.md,
              backgroundColor: operatorControlsEnabled ? theme.colors.surface2 : theme.colors.surface1,
              borderWidth: 1,
              borderColor: operatorControlsEnabled ? theme.colors.violet : theme.colors.border,
              alignItems: "center",
            }}
          >
            <Text style={{ color: theme.colors.text, fontWeight: "900" }}>dry_run: {String(Boolean(settings["dry_run"]))}</Text>
          </Pressable>

          <View
            style={{
              flexBasis: "48%",
              paddingVertical: 12,
              borderRadius: theme.radii.md,
              backgroundColor: theme.colors.surface1,
              borderWidth: 1,
              borderColor: kellyEnabled ? theme.colors.good : theme.colors.border,
              alignItems: "center",
            }}
          >
            <Text style={{ color: kellyEnabled ? theme.colors.good : theme.colors.textMuted, fontWeight: "900" }}>kelly_enabled: {String(kellyEnabled)}</Text>
          </View>

          <Pressable
            disabled={!operatorControlsEnabled}
            onPress={() => patchSettings({ send_mode: settings["send_mode"] === "flashbots" ? "public" : "flashbots" })}
            style={{
              flexBasis: "48%",
              paddingVertical: 12,
              borderRadius: theme.radii.md,
              backgroundColor: theme.colors.surface1,
              borderWidth: 1,
              borderColor: theme.colors.border,
              alignItems: "center",
              opacity: operatorControlsEnabled ? 1 : 0.5,
            }}
          >
            <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>send_mode: {String(settings["send_mode"] ?? "-")}</Text>
          </Pressable>

          <Pressable
            disabled={!operatorControlsEnabled}
            onPress={() => {
              const modes = ["off", "shadow", "suggest", "auto"];
              const idx = Math.max(0, modes.indexOf(brainMode));
              const next = modes[(idx + 1) % modes.length];
              patchSettings({ brain_mode: next });
            }}
            style={{
              flexBasis: "48%",
              paddingVertical: 12,
              borderRadius: theme.radii.md,
              backgroundColor: theme.colors.surface1,
              borderWidth: 1,
              borderColor: theme.colors.border,
              alignItems: "center",
              opacity: operatorControlsEnabled ? 1 : 0.5,
            }}
          >
            <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>brain_mode: {brainMode}</Text>
          </Pressable>

          <Pressable
            disabled={!operatorControlsEnabled}
            onPress={() => patchSettings({ gas_mode: settings["gas_mode"] === "aggressive" ? "normal" : "aggressive" })}
            style={{
              flexBasis: "48%",
              paddingVertical: 12,
              borderRadius: theme.radii.md,
              backgroundColor: theme.colors.surface1,
              borderWidth: 1,
              borderColor: theme.colors.border,
              alignItems: "center",
              opacity: operatorControlsEnabled ? 1 : 0.5,
            }}
          >
            <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>gas_mode: {String(settings["gas_mode"] ?? "-")}</Text>
          </Pressable>
        </View>

        <View style={{ flexDirection: "row", gap: 10, marginTop: theme.spacing.md }}>
          <Pressable
            onPress={() => void refreshMultichain()}
            style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1, alignItems: "center" }}
          >
            <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>Refresh chains</Text>
          </Pressable>

          <Pressable
            disabled={!operatorControlsEnabled}
            onPress={() => void patchSettings({ auto_trading: false })}
            style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.danger, alignItems: "center", opacity: operatorControlsEnabled ? 1 : 0.5 }}
          >
            <Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>Emergency Stop</Text>
          </Pressable>
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Active chain</Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
            {(multichain.chains.length ? multichain.chains : [chainLabel]).slice(0, 12).map((c) => {
              const active = String(c) === chainLabel;
              return (
                <Pressable
                  key={c}
                  disabled={!operatorControlsEnabled}
                  onPress={() => void selectActiveChain(String(c))}
                  style={{
                    paddingHorizontal: 10,
                    paddingVertical: 8,
                    borderRadius: theme.radii.pill,
                    borderWidth: 1,
                    borderColor: active ? theme.colors.cyan : theme.colors.border,
                    backgroundColor: active ? theme.colors.surface2 : theme.colors.surface1,
                    opacity: operatorControlsEnabled ? 1 : 0.5,
                  }}
                >
                  <Text style={{ color: active ? theme.colors.text : theme.colors.textMuted, ...theme.typography.mono }}>{String(c).toUpperCase()}</Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      </SurfaceCard>
    </ScrollView>
  );
}
