import React from 'react';
import { View, Text } from 'react-native';
import { useTheme } from '../../../utils/useTheme';

type Segment = { label: string; value: number; color?: string };

export function StackedBarChart({ title, segments }: { title?: string; segments: Segment[] }) {
  const theme = useTheme();
  const safe = segments.map((segment, idx) => ({
    ...segment,
    value: Math.max(0, Number.isFinite(segment.value) ? segment.value : 0),
    color: segment.color ?? [theme.colors.cyan, theme.colors.violet, theme.colors.good, theme.colors.warn, theme.colors.danger][idx % 5],
  }));
  const total = safe.reduce((sum, segment) => sum + segment.value, 0) || 1;

  return (
    <View>
      {title ? <Text style={{ color: theme.colors.textMuted, fontSize: 12, fontWeight: '800', marginBottom: 8 }}>{title}</Text> : null}
      <View style={{ height: 16, flexDirection: 'row', overflow: 'hidden', borderRadius: 999, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
        {safe.map((segment) => (
          <View key={segment.label} style={{ width: `${(segment.value / total * 100).toFixed(2)}%`, backgroundColor: segment.color }} />
        ))}
      </View>
      <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        {safe.map((segment) => (
          <View key={`${segment.label}-legend`} style={{ minWidth: 120, flexGrow: 1, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ width: 10, height: 10, borderRadius: 999, backgroundColor: segment.color }} />
            <Text style={{ color: theme.colors.textMuted, fontSize: 12, fontWeight: '700' }}>{segment.label} {segment.value.toFixed(1)}%</Text>
          </View>
        ))}
      </View>
    </View>
  );
}
