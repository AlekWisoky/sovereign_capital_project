import React from 'react';
import { ScrollView, Text, View } from 'react-native';
import { useTheme } from '../utils/useTheme';
import { pageContentContainerStyle, pageShellStyle } from '../utils/layout';
import { SurfaceCard } from '../components/v2/SurfaceCard';
import { useStore } from '../state/store';
import { useCanonicalFeed } from '../domain/useCanonicalFeed';

export function CanonicalOmarScreen() {
  const theme = useTheme();
  const { state } = useStore();
  const feed = useCanonicalFeed(state.baseUrl, state.role === 'operator' ? state.adminKey : undefined, state.ccRefreshMs ?? 4500);
  const omar = feed.snapshot?.omar;
  const decisions = feed.snapshot?.activity.decisions ?? [];

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 40)}>
      <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>OMAR</Text>
      <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Recommendation and learning intelligence. OMAR is not the canonical decision or settlement authority.</Text>
      <View style={{ marginTop: 12, padding: 10, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
        <Text style={{ color: theme.colors.text, fontWeight: '900' }}>BACKEND · {feed.freshness.toUpperCase()}</Text>
        <Text style={{ color: theme.colors.textFaint, marginTop: 4 }}>{feed.error || 'Learning remains downstream of verified settlement.'}</Text>
      </View>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="violet">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Current recommendation</Text>
        <Text style={{ color: theme.colors.text, fontSize: 22, fontWeight: '900', marginTop: 10 }}>{omar?.recommendation ?? omar?.action ?? 'No recommendation available'}</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 8 }}>Mode: {omar?.mode ?? 'unknown'} · size preference: {omar?.sizePreference == null ? '—' : `${omar.sizePreference.toFixed(2)}x`} · gas: {omar?.gasPreference ?? '—'}</Text>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Learning gate</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 8 }}>{omar?.learningEligible ? 'Eligible for learning' : 'Learning not currently eligible'}</Text>
        <Text style={{ color: theme.colors.textFaint, marginTop: 6 }}>Reason: {omar?.learningReasonCode ?? 'awaiting canonical settlement truth'}</Text>
        <Text style={{ color: theme.colors.textFaint, marginTop: 6 }}>Last decision: {omar?.lastDecisionId ?? '—'}</Text>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Recent decision lineage</Text>
        {decisions.length === 0 ? <Text style={{ color: theme.colors.textMuted, marginTop: 8 }}>No recent XAI decisions returned.</Text> : decisions.slice(0, 8).map((decision, index) => (
          <View key={decision.decisionId ?? String(index)} style={{ marginTop: 10, padding: 10, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
            <Text style={{ color: theme.colors.text, fontWeight: '900' }}>{decision.decisionId ?? 'decision unavailable'}</Text>
            <Text style={{ color: theme.colors.textFaint, marginTop: 4 }}>{decision.action ?? '—'} · {decision.strategyFamily ?? '—'} · expected {decision.expectedNetProfitUsd == null ? '—' : `$${decision.expectedNetProfitUsd.toFixed(2)}`}</Text>
          </View>
        ))}
      </SurfaceCard>
    </ScrollView>
  );
}
