import React from 'react';
import { ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useTheme } from '../utils/useTheme';
import { pageContentContainerStyle, pageShellStyle } from '../utils/layout';
import { SurfaceCard } from '../components/v2/SurfaceCard';
import { useStore } from '../state/store';
import { useCanonicalFeed } from '../domain/useCanonicalFeed';

export function CanonicalOpportunitiesScreen() {
  const theme = useTheme();
  const navigation = useNavigation<any>();
  const { state } = useStore();
  const feed = useCanonicalFeed(state.baseUrl, state.role === 'operator' ? state.adminKey : undefined, state.ccRefreshMs ?? 4500);
  const opportunities = feed.snapshot?.opportunities ?? [];

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 40)}>
      <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Opportunities</Text>
      <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Market opportunity → canonical decision → admission. This surface is read-only.</Text>
      <View style={{ marginTop: 12, padding: 10, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
        <Text style={{ color: theme.colors.text, fontWeight: '900' }}>{feed.freshness.toUpperCase()}</Text>
        <Text style={{ color: theme.colors.textFaint, marginTop: 4 }}>{feed.error || `${opportunities.length} opportunities from backend truth`}</Text>
      </View>

      <View style={{ height: theme.spacing.md }} />
      {opportunities.length === 0 ? (
        <SurfaceCard glow="none">
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>No current opportunities</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 8 }}>The backend may be unavailable, the spread surface may be empty, or all candidates may currently be blocked.</Text>
        </SurfaceCard>
      ) : opportunities.map((opp, index) => (
        <View key={opp.id ?? opp.routeId ?? String(index)} style={{ marginBottom: theme.spacing.md }}>
          <SurfaceCard glow={opp.blocked ? 'none' : 'cyan'}>
            <Text style={{ color: theme.colors.text, fontWeight: '900', fontSize: 17 }}>{opp.title ?? opp.family ?? 'Opportunity'}</Text>
            <Text style={{ color: theme.colors.textFaint, marginTop: 4 }}>{opp.strategyFamily ?? opp.family ?? 'unknown family'} · {opp.routeId ?? 'route unavailable'}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
              <Metric label="Expected net" value={opp.expectedNetProfitUsd == null ? '—' : `$${opp.expectedNetProfitUsd.toFixed(2)}`} theme={theme} />
              <Metric label="ROI" value={opp.expectedRoiPct == null ? '—' : `${opp.expectedRoiPct.toFixed(2)}%`} theme={theme} />
              <Metric label="Confidence" value={opp.confidence == null ? '—' : `${(opp.confidence * 100).toFixed(0)}%`} theme={theme} />
              <Metric label="Required capital" value={opp.requiredCapitalUsd == null ? '—' : `$${opp.requiredCapitalUsd.toLocaleString()}`} theme={theme} />
            </View>
            <Text style={{ color: opp.blocked ? theme.colors.danger : theme.colors.textMuted, marginTop: 12, fontWeight: '800' }}>
              {opp.blocked ? `BLOCKED${opp.reasonCodes?.length ? ` · ${opp.reasonCodes.join(', ')}` : ''}` : opp.admitted ? 'ADMITTED' : 'AWAITING CANONICAL ADMISSION'}
            </Text>
            {opp.decisionId ? (
              <TouchableOpacity
                onPress={() => navigation.getParent()?.navigate('DecisionDetail', { decisionId: opp.decisionId })}
                style={{ marginTop: 14, padding: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface2, borderWidth: 1, borderColor: theme.colors.border }}
              >
                <Text style={{ color: theme.colors.cyan, fontWeight: '900' }}>View canonical decision</Text>
              </TouchableOpacity>
            ) : null}
          </SurfaceCard>
        </View>
      ))}
    </ScrollView>
  );
}

function Metric({ label, value, theme }: { label: string; value: string; theme: ReturnType<typeof useTheme> }) {
  return (
    <View style={{ minWidth: 130, flexGrow: 1, padding: 10, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
      <Text style={{ color: theme.colors.textFaint, fontSize: 11, fontWeight: '800' }}>{label}</Text>
      <Text style={{ color: theme.colors.text, marginTop: 5, fontWeight: '900' }}>{value}</Text>
    </View>
  );
}
