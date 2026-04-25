import React, { useMemo, useState } from 'react';
import { ScrollView, Text, View } from 'react-native';
import { launchFamilyDetail, pauseLaunchFamily, quarantineLaunchFamily, revertLaunchFamily, enableNextFamily } from '../api/launchApi';
import { useCommandCenter } from '../commandCenter/useCommandCenter';
import { FamilyReadinessCard } from '../components/FamilyReadinessCard';
import { useStore } from '../state/store';
import { useTheme } from '../utils/useTheme';
import { pageContentContainerStyle, pageShellStyle } from '../utils/layout';
import { SurfaceCard } from '../components/v2/SurfaceCard';
import { HeatMatrixChart } from '../components/v2/charts/HeatMatrixChart';

export function FamilyReadinessScreen() {
  const theme = useTheme();
  const cc = useCommandCenter();
  const { state } = useStore();
  const adminKey = state.role === 'operator' ? state.adminKey : undefined;
  const [detail, setDetail] = useState('');

  const families = cc.snapshot?.launch?.families ?? [];
  const matrixCells = useMemo(() => families.map((item) => ({ label: item.family.replace(/_/g, ' '), value: item.score, subtitle: `${item.status} · ${item.riskLevel ?? 'n/a'}` })), [families]);

  async function inspectFamily(family: string) {
    const resp = await launchFamilyDetail(state.baseUrl, family, adminKey);
    const item = (resp as { item?: { blockers?: string[]; reasons?: string[]; suggestedNextAction?: string; degradedState?: string; currentHealthState?: string } }).item;
    setDetail(item ? `${family}: ${(item.blockers ?? item.reasons ?? []).join(', ') || 'no blockers'} · ${item.suggestedNextAction ?? 'hold'} · ${item.currentHealthState ?? item.degradedState ?? 'live'}` : 'No detail available');
  }

  async function pauseFamily(family: string) {
    await pauseLaunchFamily(state.baseUrl, family, adminKey);
    await cc.refresh();
  }

  async function revertFamily(family: string) {
    await revertLaunchFamily(state.baseUrl, family, adminKey);
    await cc.refresh();
  }

  async function quarantineFamily(family: string) {
    await quarantineLaunchFamily(state.baseUrl, family, 'operator_quarantine', adminKey);
    await cc.refresh();
  }

  async function enableFamily(family: string) {
    await enableNextFamily(state.baseUrl, family, adminKey);
    await cc.refresh();
  }

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 40)}>
      <Text style={{ color: theme.colors.text, ...theme.typography.title }}>Family Readiness</Text>
      <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Inspect readiness, blockers, degraded states, and rollback actions family by family.</Text>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="cyan">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Readiness Heat Grid</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Structured operator view across readiness, scale posture, and risk semantics.</Text>
        <View style={{ marginTop: theme.spacing.md }}>
          <HeatMatrixChart cells={matrixCells} columns={2} />
        </View>
      </SurfaceCard>

      {(families ?? []).map((item) => (
        <FamilyReadinessCard
          key={item.family}
          item={item}
          onInspect={(family) => void inspectFamily(family)}
          onEnable={(family) => void enableFamily(family)}
          onPause={(family) => void pauseFamily(family)}
          onRevert={(family) => void revertFamily(family)}
          onQuarantine={(family) => void quarantineFamily(family)}
        />
      ))}
      {detail ? <Text style={{ color: theme.colors.textFaint, marginTop: 12 }}>{detail}</Text> : null}
    </ScrollView>
  );
}
