import React from 'react';
import { View, Text } from 'react-native';
import { useTheme } from '../../../utils/useTheme';

type Row = { label: string; value: number; subValue?: string; tone?: 'cyan' | 'violet' | 'good' | 'warn' | 'danger' };

export function HorizontalBarChart({ rows, max = 100, compact = false }: { rows: Row[]; max?: number; compact?: boolean }) {
  const theme = useTheme();
  const height = compact ? 8 : 10;
  const safeMax = max > 0 ? max : 100;

  return (
    <View style={{ gap: compact ? 10 : 12 }}>
      {rows.map((row) => {
        const pct = Math.max(0, Math.min(1, row.value / safeMax));
        const color = row.tone === 'violet' ? theme.colors.violet : row.tone === 'good' ? theme.colors.good : row.tone === 'warn' ? theme.colors.warn : row.tone === 'danger' ? theme.colors.danger : theme.colors.cyan;
        return (
          <View key={row.label}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 }}>
              <Text style={{ color: theme.colors.text, fontWeight: '800', fontSize: compact ? 12 : 13 }}>{row.label}</Text>
              <Text style={{ color: theme.colors.textMuted, fontWeight: '700', fontSize: 12 }}>{row.subValue ?? `${row.value.toFixed(1)}`}</Text>
            </View>
            <View style={{ height, borderRadius: 999, overflow: 'hidden', backgroundColor: theme.colors.surface2, borderWidth: 1, borderColor: theme.colors.border }}>
              <View style={{ width: `${(pct * 100).toFixed(1)}%`, height: '100%', borderRadius: 999, backgroundColor: color }} />
            </View>
          </View>
        );
      })}
    </View>
  );
}
