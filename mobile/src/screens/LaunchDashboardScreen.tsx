import React, { useMemo } from 'react';
import { ScrollView, Text, View, Pressable } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useCommandCenter } from '../commandCenter/useCommandCenter';
import { LaunchRecommendationCard } from '../components/LaunchRecommendationCard';
import { useTheme } from '../utils/useTheme';
import { pageContentContainerStyle, pageShellStyle } from '../utils/layout';
import { launchRecoveryFreshnessLine, launchRecoveryHistoryLine, launchRecoveryLine, launchRecoveryReliabilityLine, launchWhyNotOverflowCount, launchWhyNotPreview } from '../utils/launch';
import { SurfaceCard } from '../components/v2/SurfaceCard';
import { HeatMatrixChart } from '../components/v2/charts/HeatMatrixChart';
import { DonutChart } from '../components/v2/charts/DonutChart';
import { FlowLaneChart } from '../components/v2/charts/FlowLaneChart';
import type { CapitalStackParamList } from '../navigation/CapitalStack';

export function LaunchDashboardScreen() {
  const theme = useTheme();
  const cc = useCommandCenter();
  const launch = cc.snapshot?.launch;
  const nav = useNavigation<NativeStackNavigationProp<CapitalStackParamList>>();

  const readinessCells = useMemo(() => {
    return (launch?.families ?? []).slice(0, 6).map((item) => ({
      label: item.family.replace(/_/g, ' '),
      value: item.score,
      subtitle: `${item.status} · ${item.currentHealthState ?? item.degradedState ?? 'n/a'}`,
    }));
  }, [launch]);

  const healthSlices = useMemo(() => {
    const families = launch?.families ?? [];
    const count = Math.max(1, families.length);
    const map = [
      { label: 'Live', value: families.filter((f) => f.currentHealthState === 'live').length / count * 100 },
      { label: 'Capped', value: families.filter((f) => f.currentHealthState === 'capped_live').length / count * 100 },
      { label: 'Observe', value: families.filter((f) => f.currentHealthState === 'observe_only').length / count * 100 },
      { label: 'Quarantine', value: families.filter((f) => f.currentHealthState === 'quarantined').length / count * 100 },
    ];
    return map;
  }, [launch]);

  const profitLanes = useMemo(() => {
    const mix = cc.snapshot?.profitMix?.families ?? [];
    if (!mix.length) return [];
    return mix.slice(0, 5).map((item) => ({ label: item.family.replace(/_/g, ' '), value: item.contributionPct, note: `RODC ${item.returnOnDeployedCapital.toFixed(2)} · scale ${Math.round(item.readinessToScale * 100)}%`, tone: item.contributionPct >= 20 ? 'good' as const : 'cyan' as const }));
  }, [cc.snapshot?.profitMix]);

  const blockedPreview = useMemo(() => launchWhyNotPreview(launch, 2), [launch]);
  const blockedOverflow = useMemo(() => launchWhyNotOverflowCount(launch, 2), [launch]);
  const recoveryLine = useMemo(() => launchRecoveryLine(launch), [launch]);
  const recoveryHistoryLine = useMemo(() => launchRecoveryHistoryLine(launch), [launch]);
  const recoveryFreshnessLine = useMemo(() => launchRecoveryFreshnessLine(launch), [launch]);
  const recoveryReliabilityLine = useMemo(() => launchRecoveryReliabilityLine(launch), [launch]);

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 40)}>
      <Text style={{ color: theme.colors.text, ...theme.typography.title }}>Launch Dashboard</Text>
      <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Mode {launch?.currentLaunchMode?.replace(/_/g, ' ') || 'V1 ONLY'} · active families {(launch?.activeFamilies ?? []).join(', ') || 'flash_arb'}</Text>

      <View style={{ flexDirection: 'row', gap: 10, marginTop: theme.spacing.md }}>
        <Pressable onPress={() => nav.navigate('LaunchSetup')} style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1, alignItems: 'center' }}>
          <Text style={{ color: theme.colors.textMuted, fontWeight: '900' }}>Wizard</Text>
        </Pressable>
        <Pressable onPress={() => nav.navigate('FamilyReadiness')} style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.cyan, alignItems: 'center' }}>
          <Text style={{ color: theme.colors.bg0, fontWeight: '900' }}>Family Readiness</Text>
        </Pressable>
      </View>

      <LaunchRecommendationCard launch={launch} />

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="cyan">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Readiness Matrix</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Top rollout candidates with score and current health state.</Text>
        <View style={{ marginTop: theme.spacing.md }}>
          <HeatMatrixChart cells={readinessCells} columns={2} />
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <SurfaceCard glow="violet" style={{ flex: 1 }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Health Graph</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6, fontSize: 12 }}>Launch-health distribution across families.</Text>
          <View style={{ marginTop: theme.spacing.md, alignItems: 'center' }}>
            <DonutChart slices={healthSlices} centerLabel="health" centerValue={`${launch?.families?.length ?? 0} fam`} />
          </View>
        </SurfaceCard>
        <SurfaceCard glow="none" style={{ flex: 1 }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Rollout Stage</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6, fontSize: 12 }}>Current posture and rollback guidance.</Text>
          <View style={{ marginTop: theme.spacing.md, gap: 10 }}>
            {[
              ['Current mode', launch?.currentLaunchMode?.replace(/_/g, ' ') || 'V1 ONLY'],
              ['Next family', launch?.nextRecommendedFamily?.replace(/_/g, ' ') || 'Hold'],
              ['Rollback', launch?.rollbackRecommendation?.replace(/_/g, ' ') || 'No rollback signal'],
            ].map(([label, value]) => (
              <View key={label} style={{ padding: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface1, borderWidth: 1, borderColor: theme.colors.border }}>
                <Text style={{ color: theme.colors.textFaint, fontSize: 11, fontWeight: '700' }}>{label}</Text>
                <Text style={{ color: theme.colors.text, marginTop: 4, fontSize: 14, fontWeight: '900' }}>{value}</Text>
              </View>
            ))}
            {recoveryLine ? (
            <Text style={{ color: theme.colors.textFaint, marginTop: 10 }}>Recovery path: {recoveryLine}</Text>
          ) : null}
          {recoveryHistoryLine ? (
            <Text style={{ color: theme.colors.textFaint, marginTop: 6 }}>Recovery history: {recoveryHistoryLine}</Text>
          ) : null}
          {recoveryFreshnessLine ? (
            <Text style={{ color: theme.colors.textFaint, marginTop: 6 }}>Recovery freshness: {recoveryFreshnessLine}</Text>
          ) : null}
          {recoveryReliabilityLine ? (
            <Text style={{ color: theme.colors.textFaint, marginTop: 6 }}>Recovery reliability: {recoveryReliabilityLine}</Text>
          ) : null}
          {blockedPreview.length ? (
              <View style={{ padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
                <Text style={{ color: theme.colors.textFaint, fontSize: 11, fontWeight: '700' }}>Blocked now</Text>
                {blockedPreview.map((line) => (
                  <Text key={line} style={{ color: theme.colors.textMuted, marginTop: 4, fontSize: 12 }}>{line}</Text>
                ))}
                {blockedOverflow ? <Text style={{ color: theme.colors.textFaint, marginTop: 6, fontSize: 11 }}>+{blockedOverflow} more blocked families in recommendation detail</Text> : null}
              </View>
            ) : null}
          </View>
        </SurfaceCard>
      </View>

      {profitLanes.length ? (
        <>
          <View style={{ height: theme.spacing.md }} />
          <SurfaceCard glow="none">
            <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Profit Mix Contribution</Text>
            <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Failure-adjusted contribution by family for rollout pacing.</Text>
            <View style={{ marginTop: theme.spacing.md }}>
              <FlowLaneChart lanes={profitLanes} />
            </View>
          </SurfaceCard>
        </>
      ) : null}

      {(launch?.families ?? []).slice(0, 3).map((item) => (
        <View key={item.family} style={{ marginTop: 12, padding: 14, borderRadius: theme.radii.lg, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
          <Text style={{ color: theme.colors.text, fontWeight: '900', fontSize: 15 }}>{item.family.replace(/_/g, ' ')}</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 4 }}>Status {item.status} · Health {item.currentHealthState ?? 'n/a'} · Score {(item.score * 100).toFixed(0)}%</Text>
          {item.suggestedNextAction ? <Text style={{ color: theme.colors.textFaint, marginTop: 6 }}>Next action: {String(item.suggestedNextAction).replace(/_/g, ' ')}</Text> : null}
          {item.recoveryNextAction && !item.recoveryReady ? <Text style={{ color: theme.colors.textFaint, marginTop: 4 }}>Recovery path: {String(item.recoveryStatus ?? item.recoveryReasonCode ?? 'degraded').replace(/_/g, ' ')} · next {String(item.recoveryNextAction).replace(/_/g, ' ')}</Text> : null}
          {item.recoveryHistoryStatus && item.recoveryHistoryStatus !== 'steady' ? <Text style={{ color: theme.colors.textFaint, marginTop: 4 }}>Recovery history: {String(item.recoveryHistoryStatus).replace(/_/g, ' ')}{item.recoveryHistoryComponent ? ` · component ${String(item.recoveryHistoryComponent).replace(/_/g, ' ')}` : ''}{item.recoveryDegradedDurationMs ? ` · for ${Math.max(1, Math.floor(Number(item.recoveryDegradedDurationMs) / 60000))}m` : ''}{item.recoveryDegradedCount ? ` · count ${String(item.recoveryDegradedCount)}` : ''}{item.recoveryDegradationSeverityClass ? ` · severity ${String(item.recoveryDegradationSeverityClass).replace(/_/g, ' ')}` : ''}</Text> : null}
          {item.recoveryFreshnessReasonCodes?.length ? <Text style={{ color: theme.colors.textFaint, marginTop: 4 }}>Recovery freshness: {item.recoveryFreshnessReasonCodes.map((value) => String(value).replace(/_/g, ' ')).join(' · ')}{item.recoveryFreshnessClass ? ` · class ${String(item.recoveryFreshnessClass).replace(/_/g, ' ')}` : ''}{item.recoveryFreshnessNextAction ? ` · next ${String(item.recoveryFreshnessNextAction).replace(/_/g, ' ')}` : ''}</Text> : null}
          {item.recoveryReliabilityClass && item.recoveryReliabilityClass !== 'stable' ? <Text style={{ color: theme.colors.textFaint, marginTop: 4 }}>Recovery reliability: {(item.recoveryReliabilityReasonCodes?.length ? item.recoveryReliabilityReasonCodes.map((value) => String(value).replace(/_/g, ' ')).join(' · ') : String(item.recoveryReliabilityClass).replace(/_/g, ' '))}{item.recoveryReliabilityClass ? ` · class ${String(item.recoveryReliabilityClass).replace(/_/g, ' ')}` : ''}{item.recoveryRecoveredFragile ? ' · recovered fragile yes' : ''}{item.recoveryReliabilityNextAction ? ` · next ${String(item.recoveryReliabilityNextAction).replace(/_/g, ' ')}` : ''}</Text> : null}
        </View>
      ))}
    </ScrollView>
  );
}
