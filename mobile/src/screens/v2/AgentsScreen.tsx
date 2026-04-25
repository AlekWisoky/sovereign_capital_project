import React, { useEffect, useMemo, useState } from "react";
import { View, Text, ScrollView, Pressable } from "react-native";
import { useTheme } from "../../utils/useTheme";
import { pageContentContainerStyle, pageShellStyle } from '../../utils/layout';
import { BrandHeader } from "../../components/v2/BrandHeader";
import { SurfaceCard } from "../../components/v2/SurfaceCard";
import { Sparkline } from "../../components/v2/charts/Sparkline";
import { useStore } from "../../state/store";
import { consensusState, behaveagentState, treasuryState, governanceState } from "../../api/client";

function asRecord(v: unknown): Record<string, unknown> | null {
  return typeof v === "object" && v !== null ? (v as Record<string, unknown>) : null;
}

function num(v: unknown, fallback: number = 0): number {
  const n = typeof v === "number" ? v : typeof v === "string" ? Number(v) : NaN;
  return Number.isFinite(n) ? n : fallback;
}

function clamp01(x: number): number {
  return Math.max(0, Math.min(1, x));
}

export function AgentsScreen() {
  const theme = useTheme();
  const { state } = useStore();
  const [cons, setCons] = useState<Record<string, unknown>>({});
  const [behave, setBehave] = useState<Record<string, unknown>>({});
  const [treasury, setTreasury] = useState<Record<string, unknown>>({});
  const [gov, setGov] = useState<Record<string, unknown>>({});
  const [scoreHist, setScoreHist] = useState<number[]>([]);

  useEffect(() => {
    let stop = false;
    const loop = async () => {
      while (!stop) {
        try {
          const c = await consensusState(state.baseUrl, state.role === "operator" ? state.adminKey : undefined);
          if (!stop) {
            setCons(c as Record<string, unknown>);
            const last = asRecord(asRecord(c)?.["last"]);
            const score = clamp01(num(last?.["score"], 0));
            setScoreHist((h) => {
              const next = [...h, score].slice(-42);
              return next;
            });
          }
        } catch {
          // ignore
        }
        try {
          const b = await behaveagentState(state.baseUrl, state.role === "operator" ? state.adminKey : undefined);
          if (!stop) setBehave(b as Record<string, unknown>);
        } catch {
          // ignore
        }
        try {
          const t = await treasuryState(state.baseUrl, state.role === "operator" ? state.adminKey : undefined);
          if (!stop) setTreasury(t as Record<string, unknown>);
        } catch {
          // ignore
        }
        try {
          const g = await governanceState(state.baseUrl, state.role === "operator" ? state.adminKey : undefined);
          if (!stop) setGov(g as Record<string, unknown>);
        } catch {
          // ignore
        }
        await new Promise((r) => setTimeout(r, 4200));
      }
    };
    void loop();
    return () => {
      stop = true;
    };
  }, [state.baseUrl, state.role, state.adminKey]);

  const last = useMemo(() => asRecord(cons?.["last"]) ?? {}, [cons]);
  const score = clamp01(num(last["score"], 0));
  const threshold = clamp01(num(last["threshold"], 0.55));
  const allow = Boolean(last["allow"]);
  const action = allow ? "SUGGEST" : "SKIP";

  const signals = asRecord(last["signals"]) ?? {};
  const confs = asRecord(last["confidences"]) ?? {};

  const tiles = useMemo(() => {
    const mk = (k: string, label: string) => {
      const v = clamp01(num(signals[k], 0));
      const c = clamp01(num(confs[k], 0));
      const tone = v * c;
      const color = tone > 0.6 ? theme.colors.good : tone > 0.35 ? theme.colors.warn : theme.colors.textMuted;
      return { key: k, label, v, c, color };
    };
    return [mk("alpha", "Alpha"), mk("risk", "Risk"), mk("treasury", "Treasury"), mk("mev", "MEV")];
  }, [signals, confs, theme.colors.good, theme.colors.warn, theme.colors.textMuted]);

  const meterW = 320;
  const scoreW = Math.round(meterW * score);
  const thrW = Math.round(meterW * threshold);

  const traceSnippet = useMemo(() => {
    const explain = last["explain"];
    if (typeof explain === "string") return explain;
    const reasons = last["reasons"];
    if (Array.isArray(reasons)) return JSON.stringify(reasons.slice(0, 6), null, 2);
    return JSON.stringify(last, null, 2);
  }, [last]);

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 24)}>
      <BrandHeader title="Agents" subtitle="Consensus + governance" rightTag={state.role === "operator" ? "OPERATOR" : "READ"} />

      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Consensus Meter</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Deterministic score vs threshold. Output drives safe execution defaults.
        </Text>

        <View style={{ marginTop: theme.spacing.md, width: meterW, height: 12, borderRadius: 999, backgroundColor: theme.colors.surface1, overflow: "hidden" }}>
          <View style={{ width: scoreW, height: 12, backgroundColor: allow ? theme.colors.good : theme.colors.warn }} />
          <View
            style={{ position: "absolute", left: thrW - 1, top: 0, width: 2, height: 12, backgroundColor: theme.colors.violet, opacity: 0.9 }}
          />
        </View>

        <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 10 }}>
          <Text style={{ color: theme.colors.textMuted, ...theme.typography.mono }}>score={score.toFixed(3)}</Text>
          <Text style={{ color: theme.colors.textMuted, ...theme.typography.mono }}>thr={threshold.toFixed(3)}</Text>
          <Text style={{ color: allow ? theme.colors.good : theme.colors.warn, ...theme.typography.mono }}>{action}</Text>
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <Sparkline width={meterW} height={40} data={scoreHist.length ? scoreHist : [0.4, 0.55, 0.6, 0.52]} tone={allow ? "good" : "neutral"} />
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />

      <SurfaceCard glow="cyan">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Agent Scoreboard</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Signal × confidence. Low confidence automatically down-weights suggestions.
        </Text>

        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: theme.spacing.md }}>
          {tiles.map((t) => (
            <View
              key={t.key}
              style={{ flexBasis: "48%", padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}
            >
              <Text style={{ color: theme.colors.textMuted, ...theme.typography.mono }}>{t.label}</Text>
              <Text style={{ color: t.color, marginTop: 6, fontSize: 18, fontWeight: "900" }}>{(t.v * t.c).toFixed(2)}</Text>
              <Text style={{ color: theme.colors.textFaint, marginTop: 4, ...theme.typography.mono }}>v={t.v.toFixed(2)} · c={t.c.toFixed(2)}</Text>
            </View>
          ))}
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />

      <SurfaceCard glow="violet">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Explain Trace</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Deterministic reasoning snippet + recommended action.
        </Text>

        <Text style={{ color: theme.colors.textMuted, marginTop: theme.spacing.md, fontFamily: "monospace" }}>{traceSnippet}</Text>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />

      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Governance & Treasury</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Human handling + governance visibility for safe autonomy.
        </Text>
        <View style={{ marginTop: theme.spacing.md }}>
          <Text style={{ color: theme.colors.textMuted, ...theme.typography.mono }}>treasury</Text>
          <Text style={{ color: theme.colors.textFaint, marginTop: 4, fontFamily: "monospace" }}>{JSON.stringify(treasury, null, 2)}</Text>
        </View>
        <View style={{ marginTop: theme.spacing.md }}>
          <Text style={{ color: theme.colors.textMuted, ...theme.typography.mono }}>governance</Text>
          <Text style={{ color: theme.colors.textFaint, marginTop: 4, fontFamily: "monospace" }}>{JSON.stringify(gov, null, 2)}</Text>
        </View>
      </SurfaceCard>
    </ScrollView>
  );
}
