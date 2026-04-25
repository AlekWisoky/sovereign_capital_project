import React, { useMemo, useState } from 'react';
import { View, Text, ScrollView, Pressable } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useTheme } from '../../utils/useTheme';
import { pageContentContainerStyle, pageShellStyle } from '../../utils/layout';
import { SurfaceCard } from '../../components/v2/SurfaceCard';
import { CompactTable, type CompactRow } from '../../components/v2/CompactTable';
import { TopStatusBar } from '../../components/cc/TopStatusBar';
import { ConfirmDialog } from '../../components/v2/ConfirmDialog';
import { useCommandCenter } from '../../commandCenter/useCommandCenter';
import type { CapitalStackParamList } from '../../navigation/CapitalStack';
import { StackedBarChart } from '../../components/v2/charts/StackedBarChart';
import { FlowLaneChart } from '../../components/v2/charts/FlowLaneChart';
import { DonutChart } from '../../components/v2/charts/DonutChart';

function usd(n: number): string {
  return `$${n.toFixed(0)}`;
}

export function CapitalArchitectureScreen() {
  const theme = useTheme();
  const cc = useCommandCenter();
  const snap = cc.snapshot;
  const nav = useNavigation<NativeStackNavigationProp<CapitalStackParamList>>();
  const [flowId, setFlowId] = useState<string | null>(null);
  const flow = useMemo(() => snap?.capitalFlows.find((x) => x.id === flowId) ?? null, [snap, flowId]);

  const rows: CompactRow[] = useMemo(() => {
    if (!snap) return [];
    return snap.allocations.map((s) => ({
      key: s.id,
      cols: [s.name, usd(s.capitalUsd), `${s.roiPct.toFixed(1)}%`, s.status.toUpperCase()],
      tone: s.status === 'active' ? 'good' : s.status === 'probation' ? 'warn' : 'neutral',
    }));
  }, [snap]);

  const bucketSegments = useMemo(() => (snap ? [
    { label: 'Execution', value: snap.exposure.activePct, color: theme.colors.cyan },
    { label: 'Reserve', value: Math.max(0, snap.exposure.idlePct - snap.exposure.atRiskPct), color: theme.colors.violet },
    { label: 'Experimental', value: snap.exposure.sandboxPct, color: theme.colors.warn },
    { label: 'Drawdown Buffer', value: snap.exposure.atRiskPct, color: theme.colors.danger },
  ] : []), [snap, theme]);

  const familyContribution = useMemo(() => {
    const items = snap?.allocations ?? [];
    const total = items.reduce((sum, item) => sum + Math.max(0, item.capitalUsd), 0) || 1;
    return items.slice(0, 4).map((item) => ({ label: item.name, value: item.capitalUsd / total * 100 }));
  }, [snap]);

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 40)}>
      <TopStatusBar title="Capital Architecture" subtitle="Where every dollar lives, and why" rightTag={cc.source === 'backend' ? 'BACKEND' : 'DEMO'} live={cc.source === 'backend'} />

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: theme.spacing.md }}>
        {[
          ['Launch Wizard', 'LaunchSetup'],
          ['Launch Dashboard', 'LaunchDashboard'],
          ['Family Readiness', 'FamilyReadiness'],
          ['Off-Ramp', 'OffRamp'],
          ['Wallet', 'Wallet'],
          ['Ledger', 'Ledger'],
        ].map(([label, route]) => (
          <Pressable key={route} onPress={() => nav.navigate(route as keyof CapitalStackParamList)} style={{ minWidth: 148, flexGrow: 1, paddingVertical: 12, paddingHorizontal: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: route === 'LaunchSetup' ? theme.colors.surface2 : theme.colors.surface1 }}>
            <Text style={{ color: route === 'LaunchSetup' ? theme.colors.cyan : theme.colors.textMuted, fontWeight: '900' }}>{label}</Text>
          </Pressable>
        ))}
      </View>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="cyan">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Bucket Architecture</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Execution, reserve, experimental, and drawdown buffer posture derived from current exposure composition.</Text>
        <View style={{ marginTop: theme.spacing.md }}>
          <StackedBarChart segments={bucketSegments} />
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <SurfaceCard glow="none" style={{ flex: 1 }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Strategy Allocations</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Family allocations, ROI, and operating status.</Text>
          <View style={{ marginTop: theme.spacing.md }}>
            <CompactTable header={['Strategy', 'Capital', 'ROI', 'Status']} rows={rows} />
          </View>
        </SurfaceCard>
        <SurfaceCard glow="violet" style={{ flex: 1 }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Capital Mix</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Top family allocation share.</Text>
          <View style={{ marginTop: theme.spacing.md, alignItems: 'center' }}>
            <DonutChart slices={familyContribution} centerLabel="capital" centerValue={`${snap?.allocations.length ?? 0} fam`} />
          </View>
        </SurfaceCard>
      </View>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Capital Flow Map</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>If you cannot explain a capital movement, freeze allocations and inspect the audit trail.</Text>
        <View style={{ marginTop: theme.spacing.md }}>
          <FlowLaneChart lanes={[
            { label: 'Idle capital', value: snap?.exposure.idlePct ?? 0, note: 'Uncommitted reserve posture', tone: 'violet' },
            { label: 'Active capital', value: snap?.exposure.activePct ?? 0, note: 'Live strategy allocation', tone: 'cyan' },
            { label: 'Sandbox', value: snap?.exposure.sandboxPct ?? 0, note: 'Research/probation capital', tone: 'warn' },
            { label: 'At-risk', value: snap?.exposure.atRiskPct ?? 0, note: 'Drawdown-sensitive capital', tone: 'danger' },
          ]} />
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />
      {snap ? (
        <SurfaceCard glow="violet">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Capital Flow Timeline</Text>
            <Pressable onPress={() => void cc.refresh()} style={{ paddingVertical: 6, paddingHorizontal: 10, borderRadius: theme.radii.pill, backgroundColor: theme.colors.surface2 }}>
              <Text style={{ color: theme.colors.textMuted, fontWeight: '900' }}>Refresh</Text>
            </Pressable>
          </View>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Tap any movement to see AI reasoning, risk validation, and execution summary.</Text>

          <View style={{ marginTop: theme.spacing.md }}>
            {snap.capitalFlows.slice(0, 10).map((e) => (
              <Pressable
                key={e.id}
                onPress={() => setFlowId(e.id)}
                style={{
                  paddingVertical: 12,
                  borderTopWidth: 1,
                  borderTopColor: theme.colors.border,
                  flexDirection: 'row',
                  justifyContent: 'space-between',
                  gap: 10,
                }}
              >
                <View style={{ flex: 1 }}>
                  <Text style={{ color: theme.colors.text, fontWeight: '900' }}>{e.from} → {e.to}</Text>
                  <Text style={{ color: theme.colors.textMuted, marginTop: 4, fontSize: 12 }}>{e.why}</Text>
                  <Text style={{ color: theme.colors.textFaint, marginTop: 6, fontSize: 11, fontFamily: 'monospace' }}>
                    Trigger: {e.triggeredBy.toUpperCase()} · Risk: {e.riskResult.toUpperCase()}
                  </Text>
                </View>
                <View style={{ alignItems: 'flex-end' }}>
                  <Text style={{ color: theme.colors.cyan, fontWeight: '900' }}>{usd(e.amountUsd)}</Text>
                  <Text style={{ color: theme.colors.textFaint, marginTop: 6, fontSize: 11 }}>Details</Text>
                </View>
              </Pressable>
            ))}
          </View>
        </SurfaceCard>
      ) : null}

      <ConfirmDialog
        visible={!!flow}
        title={flow ? `Movement · ${usd(flow.amountUsd)}` : 'Movement'}
        body={flow ? `Triggered by: ${flow.triggeredBy}\n\nWHY: ${flow.why}\n\nRisk validation: ${flow.riskResult}\n\nExecution: ${flow.execSummary ?? '(n/a)'}` : ''}
        confirmText="Close"
        cancelText="Close"
        onCancel={() => setFlowId(null)}
        onConfirm={() => setFlowId(null)}
      />
    </ScrollView>
  );
}
