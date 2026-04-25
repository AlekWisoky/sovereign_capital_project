import React, { useMemo } from 'react';
import { View, Text, ScrollView } from 'react-native';
import { useTheme } from '../../utils/useTheme';
import { pageContentContainerStyle, pageShellStyle } from '../../utils/layout';
import { SurfaceCard } from '../../components/v2/SurfaceCard';
import { TopStatusBar } from '../../components/cc/TopStatusBar';
import { EquityCurveChart } from '../../components/cc/charts/EquityCurveChart';
import { LiveModeBanner } from '../../components/cc/LiveModeBanner';
import { useCommandCenter } from '../../commandCenter/useCommandCenter';
import { MultiLineChart } from '../../components/cc/charts/MultiLineChart';
import { HorizontalBarChart } from '../../components/v2/charts/HorizontalBarChart';
import { DonutChart } from '../../components/v2/charts/DonutChart';
import { RadialGauge } from '../../components/v2/charts/RadialGauge';
import { Sparkline } from '../../components/v2/charts/Sparkline';
import { endpointRankingRows, endpointUniverseRows, liveFragilitySummary, routeQualityRows } from '../../commandCenter/executionSummary';

export function PerformanceScreen() {
  const theme = useTheme();
  const cc = useCommandCenter();
  const snap = cc.snapshot;

  const realizedSeries = useMemo(() => (snap?.analytics.realizedAfterGas ?? []).map((row) => row.valueUsd), [snap?.analytics.realizedAfterGas]);
  const drawdownSeries = useMemo(() => (snap?.analytics.drawdown ?? []).map((row) => row.drawdownPct), [snap?.analytics.drawdown]);
  const profitMix = useMemo(() => (snap?.profitMix?.families ?? []).slice(0, 5).map((item) => ({ label: item.family.replace(/_/g, ' '), value: item.contributionPct })), [snap?.profitMix]);
  const laneRows = useMemo(() => (snap?.analytics.laneSuccess ?? []).slice(0, 5).map((row) => ({ label: row.lane, value: row.successPct, subValue: `${row.successPct.toFixed(1)}%`, tone: row.successPct >= 70 ? 'good' as const : row.successPct >= 45 ? 'warn' as const : 'danger' as const })), [snap?.analytics.laneSuccess]);
  const venueRows = useMemo(() => (snap?.analytics.venueQuality ?? []).slice(0, 5).map((row) => ({ label: row.venue, value: row.quality * 100, subValue: row.quality.toFixed(2), tone: row.quality >= 0.75 ? 'good' as const : row.quality >= 0.55 ? 'warn' as const : 'danger' as const })), [snap?.analytics.venueQuality]);
  const latencyA = useMemo(() => [snap?.observability.execLatencyMsP50 ?? 0, snap?.observability.execLatencyMsP90 ?? 0, snap?.observability.execLatencyMsP99 ?? 0], [snap?.observability]);
  const latencyB = useMemo(() => [snap?.observability.submitToReceiptMsP50 ?? 0, snap?.observability.submitToReceiptMsP90 ?? 0, snap?.observability.submitToReceiptMsP99 ?? 0], [snap?.observability]);
  const endpointRows = useMemo(() => { const rows = endpointRankingRows(snap); return rows.length ? rows : [{ lane: 'none', endpoint: 'No endpoint data', score: 0, avgLatencyMs: 0, successRate: 0, relay: false }]; }, [snap]);
  const endpointUniverse = useMemo(() => { const rows = endpointUniverseRows(snap); return rows.length ? rows : [{ bucket: 'none', lane: 'NONE', endpoint: 'No endpoint universe', source: 'n/a', privacyClass: 'public', preferred: false, reason: 'awaiting backend data' }]; }, [snap]);
  const routeRows = useMemo(() => { const rows = routeQualityRows(snap).map((row) => ({ label: row.label, value: row.quality * 100, subValue: `${(row.successRate * 100).toFixed(0)}% · $${row.meanEdgeUsd.toFixed(2)}`, tone: row.quality >= 0.8 ? 'good' as const : row.quality >= 0.6 ? 'warn' as const : 'danger' as const })); return rows.length ? rows : [{ label: 'No route-quality data', value: 0, subValue: 'awaiting outcomes', tone: 'warn' as const }]; }, [snap]);
  const fragility = useMemo(() => liveFragilitySummary(snap), [snap]);

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 40)}>
      <TopStatusBar title="Analytics" subtitle="Equity, realized PnL, execution quality, and operator-grade performance telemetry" rightTag={cc.source === 'backend' ? 'BACKEND' : 'DEMO'} live={cc.source === 'backend'} />

      <View style={{ height: theme.spacing.md }} />
      <LiveModeBanner mode={(snap?.liveMode ?? (cc.source === 'backend' ? 'backend-mock' : 'demo')) as any} sourceLabel={snap?.sourceLabel} />

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="cyan">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>NAV / Equity Curve</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Walk-forward equity with regime overlay and realized-after-gas context.</Text>
        <View style={{ marginTop: theme.spacing.md }}>
          <EquityCurveChart data={snap?.analytics.equity ?? []} height={164} />
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <SurfaceCard glow="violet" style={{ flex: 1 }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Realized After Gas</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6, fontSize: 12 }}>Capture matters more than quoted edge.</Text>
          <View style={{ marginTop: theme.spacing.md }}>
            <Sparkline width={140} height={42} data={realizedSeries.length ? realizedSeries : [0, 0]} tone="good" />
          </View>
          <Text style={{ color: theme.colors.text, marginTop: 10, fontWeight: '900', fontSize: 18 }}>${Number(realizedSeries.slice(-1)[0] ?? 0).toFixed(2)}</Text>
        </SurfaceCard>
        <SurfaceCard glow="none" style={{ flex: 1 }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Drawdown</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6, fontSize: 12 }}>Bounded drawdown is a first-class product promise.</Text>
          <View style={{ marginTop: theme.spacing.md }}>
            <Sparkline width={140} height={42} data={drawdownSeries.length ? drawdownSeries : [0, 0]} tone="danger" />
          </View>
          <Text style={{ color: theme.colors.text, marginTop: 10, fontWeight: '900', fontSize: 18 }}>{Number(drawdownSeries.slice(-1)[0] ?? 0).toFixed(2)}%</Text>
        </SurfaceCard>
      </View>

      <View style={{ height: theme.spacing.md }} />
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <SurfaceCard glow="none" style={{ flex: 1 }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Return per Risk</Text>
          <View style={{ marginTop: theme.spacing.md, alignItems: 'center' }}>
            <RadialGauge value={(snap?.analytics.returnPerRisk ?? 0) * 25} max={100} label="return/risk" subtitle={(snap?.analytics.returnPerRisk ?? 0).toFixed(2)} tone="cyan" />
          </View>
        </SurfaceCard>
        <SurfaceCard glow="none" style={{ flex: 1 }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Profit Mix</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6, fontSize: 12 }}>Family contribution to realized profitability.</Text>
          <View style={{ marginTop: theme.spacing.md, alignItems: 'center' }}>
            <DonutChart slices={profitMix.length ? profitMix : [{ label: 'No data', value: 100 }]} centerLabel="mix" centerValue={`${snap?.profitMix?.totalRealizedPnlUsd?.toFixed(0) ?? 0}`} />
          </View>
        </SurfaceCard>
      </View>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="violet">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Execution + Receipt Latency</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>p50/p90/p99 execution timing versus submit-to-receipt timing.</Text>
        <View style={{ marginTop: theme.spacing.md }}>
          <MultiLineChart a={latencyA} b={latencyB} height={140} />
        </View>
        <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap', marginTop: theme.spacing.md }}>
          {[
            ['Loop p50', `${Math.round(snap?.observability.loopMsP50 ?? 0)} ms`],
            ['Loop p90', `${Math.round(snap?.observability.loopMsP90 ?? 0)} ms`],
            ['Loop p99', `${Math.round(snap?.observability.loopMsP99 ?? 0)} ms`],
            ['Receipt p50', `${Math.round(snap?.observability.submitToReceiptMsP50 ?? 0)} ms`],
          ].map(([label, value]) => (
            <View key={label} style={{ minWidth: 140, flexGrow: 1, padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
              <Text style={{ color: theme.colors.textFaint, fontSize: 11, fontWeight: '700' }}>{label}</Text>
              <Text style={{ color: theme.colors.text, marginTop: 6, fontWeight: '900' }}>{value}</Text>
            </View>
          ))}
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <SurfaceCard glow="none" style={{ flex: 1 }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Lane Success</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Success by routing lane.</Text>
          <View style={{ marginTop: theme.spacing.md }}>
            <HorizontalBarChart rows={laneRows} max={100} />
          </View>
        </SurfaceCard>
        <SurfaceCard glow="none" style={{ flex: 1 }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Venue Quality</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Empirical venue quality feedback.</Text>
          <View style={{ marginTop: theme.spacing.md }}>
            <HorizontalBarChart rows={venueRows} max={100} />
          </View>
        </SurfaceCard>
      </View>


      <View style={{ height: theme.spacing.md }} />
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <SurfaceCard glow="none" style={{ flex: 1 }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Endpoint Health + Lane Routing</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Ranked live endpoints and relays used for send-lane selection.</Text>
          <View style={{ marginTop: theme.spacing.md }}>
            <HorizontalBarChart rows={endpointRows.map((row) => ({ label: `${row.lane} · ${row.endpoint}`, value: row.score * 100, subValue: `${Math.round(row.avgLatencyMs)} ms · ${(row.successRate * 100).toFixed(0)}%`, tone: row.score >= 0.8 ? 'good' as const : row.score >= 0.6 ? 'warn' as const : 'danger' as const }))} max={100} />
          </View>
        </SurfaceCard>
        <SurfaceCard glow="none" style={{ flex: 1 }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Route Quality + Fallback Readiness</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Realized venue-subset quality and active fallback posture.</Text>
          <View style={{ marginTop: theme.spacing.md }}>
            <HorizontalBarChart rows={routeRows} max={100} />
          </View>
          <Text style={{ color: theme.colors.textFaint, marginTop: 10 }}>Most fragile live route · {fragility.routeFamily || 'none'} · interference {(fragility.fragility * 100).toFixed(0)}% · provider {fragility.provider || 'n/a'}{(fragility as any).providerChoiceReason ? ` (${String((fragility as any).providerChoiceReason).replace(/_/g, ' ')})` : ''} · size {Number((fragility as any).sizeMult ?? 1).toFixed(2)}x / borrow {Number((fragility as any).borrowMult ?? 1).toFixed(2)}x · fallback {fragility.fallbackReady ? 'ready' : 'no'}</Text>
        </SurfaceCard>
      </View>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Endpoint Universe + Selection</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>Configured endpoint universe, privacy class, operator preference, and selection context used on the live execution path.</Text>
        <View style={{ marginTop: theme.spacing.md, gap: 8 }}>
          {endpointUniverse.slice(0, 6).map((row) => (
            <View key={`${row.bucket}-${row.endpoint}`} style={{ padding: 12, borderRadius: theme.radii.lg, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
              <Text style={{ color: theme.colors.text, fontWeight: '900' }}>{row.lane} · {row.endpoint}</Text>
              <Text style={{ color: theme.colors.textFaint, marginTop: 4, ...theme.typography.mono }}>{row.privacyClass} · {row.source}{row.preferred ? ' · preferred' : ''}</Text>
              <Text style={{ color: theme.colors.textMuted, marginTop: 4, ...theme.typography.body }}>{row.reason}</Text>
            </View>
          ))}
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Efficiency Dashboard</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>These metrics help you win on realized PnL, not theoretical edge.</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: theme.spacing.sm, marginTop: theme.spacing.md }}>
          <Metric label="Utilization" value={`${(snap?.analytics.utilizationPct ?? 0).toFixed(0)}%`} data={[snap?.analytics.utilizationPct ?? 0, snap?.analytics.utilizationPct ?? 0.8 * (snap?.analytics.utilizationPct ?? 0)]} tone="neutral" />
          <Metric label="Exec Success" value={`${(snap?.analytics.execSuccessPct ?? 0).toFixed(0)}%`} data={[snap?.analytics.execSuccessPct ?? 0, snap?.analytics.execSuccessPct ?? 0.85 * (snap?.analytics.execSuccessPct ?? 0)]} tone="good" />
          <Metric label="Slippage" value={`${(snap?.analytics.slippagePct ?? 0).toFixed(2)}%`} data={[snap?.analytics.slippagePct ?? 0, snap?.analytics.slippagePct ?? 0.9 * (snap?.analytics.slippagePct ?? 0)]} tone="danger" />
          <Metric label="Complexity Cost" value={(snap?.analytics.complexityCost ?? 0).toFixed(2)} data={[snap?.analytics.complexityCost ?? 0, snap?.analytics.complexityCost ?? 0.75 * (snap?.analytics.complexityCost ?? 0)]} tone="warn" />
        </View>
      </SurfaceCard>


      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="none"> 
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Runtime Services</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Admission, execution, receipt, and telemetry service summaries from the live backend.</Text>
        <View style={{ marginTop: theme.spacing.md, gap: 10 }}>
          {[
            ['Admission', snap?.services?.admission],
            ['Execution', snap?.services?.execution],
            ['Receipt', snap?.services?.receipt],
            ['Telemetry', snap?.services?.telemetry],
            ['Wealth Goal', snap?.services?.wealthGoal],
          ].map(([label, svc]) => (
            <View key={String(label)} style={{ padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
              <Text style={{ color: theme.colors.text, fontWeight: '900' }}>{String(label)}</Text>
              <Text style={{ color: theme.colors.textFaint, marginTop: 6 }}>{svc ? JSON.stringify(svc) : 'No service summary available'}</Text>
            </View>
          ))}
        </View>
      </SurfaceCard>

    </ScrollView>
  );
}

function Metric({ label, value, data, tone }: { label: string; value: string; data: number[]; tone: 'neutral' | 'good' | 'warn' | 'danger' }) {
  const theme = useTheme();
  return (
    <View style={{ flexGrow: 1, minWidth: 150, padding: 12, borderRadius: theme.radii.lg, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
      <Text style={{ color: theme.colors.textFaint, fontSize: 11, fontWeight: '700' }}>{label}</Text>
      <Text style={{ color: theme.colors.text, marginTop: 6, fontWeight: '900', fontSize: 18 }}>{value}</Text>
      <View style={{ marginTop: 10 }}>
        <Sparkline width={120} height={26} data={data} tone={tone} />
      </View>
    </View>
  );
}
