import React from 'react';
import { Text, View } from 'react-native';
import type { LaunchSummary } from '../commandCenter/types';
import { launchWhyNotLines } from '../utils/launch';
import { useTheme } from '../utils/useTheme';

export function LaunchRecommendationCard({ launch }: { launch?: LaunchSummary | null }) {
  const theme = useTheme();
  if (!launch) return null;
  const whyNow = launch.recommendation?.whyNow ?? launch.reasons ?? [];
  const whyNot = launchWhyNotLines(launch);
  return (
    <View style={{ padding: 14, borderRadius: theme.radii.lg, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1, marginTop: 12 }}>
      <Text style={{ color: theme.colors.textFaint, fontSize: 12, fontWeight: '800' }}>Recommended next family</Text>
      <Text style={{ color: theme.colors.text, marginTop: 6, fontSize: 20, fontWeight: '900' }}>{launch.nextRecommendedFamily ? launch.nextRecommendedFamily.replace(/_/g, ' ') : 'Hold current stage'}</Text>
      {whyNow.length ? <Text style={{ color: theme.colors.textMuted, marginTop: 8, fontSize: 12 }}>Why now: {whyNow.join(' · ')}</Text> : null}
      {whyNot.length ? <Text style={{ color: theme.colors.textFaint, marginTop: 8, fontSize: 12 }}>Why not others: {whyNot.join(' · ')}</Text> : null}
      {launch.rollbackRecommendation ? <Text style={{ color: theme.colors.warn, marginTop: 8, fontSize: 12 }}>Rollback recommendation: {launch.rollbackRecommendation.replace(/_/g, ' ')}</Text> : null}
    </View>
  );
}
