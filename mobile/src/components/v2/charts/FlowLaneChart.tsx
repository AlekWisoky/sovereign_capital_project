import React from 'react';
import { View, Text } from 'react-native';
import { useTheme } from '../../../utils/useTheme';

type Lane = { label: string; value: number; note?: string; tone?: 'cyan' | 'violet' | 'good' | 'warn' | 'danger' };

export function FlowLaneChart({ title, lanes }: { title?: string; lanes: Lane[] }) {
  const theme = useTheme();
  const total = lanes.reduce((sum, lane) => sum + Math.max(0, lane.value), 0) || 1;
  return (
    <View>
      {title ? <Text style={{ color: theme.colors.textMuted, fontSize: 12, fontWeight: '800', marginBottom: 10 }}>{title}</Text> : null}
      <View style={{ gap: 10 }}>
        {lanes.map((lane) => {
          const pct = Math.max(0, lane.value) / total;
          const color = lane.tone === 'violet' ? theme.colors.violet : lane.tone === 'good' ? theme.colors.good : lane.tone === 'warn' ? theme.colors.warn : lane.tone === 'danger' ? theme.colors.danger : theme.colors.cyan;
          return (
            <View key={lane.label} style={{ padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 10 }}>
                <Text style={{ color: theme.colors.text, fontWeight: '900' }}>{lane.label}</Text>
                <Text style={{ color, fontWeight: '900' }}>{lane.value.toFixed(1)}%</Text>
              </View>
              <View style={{ marginTop: 8, height: 10, borderRadius: 999, overflow: 'hidden', backgroundColor: theme.colors.surface2 }}>
                <View style={{ width: `${(pct * 100).toFixed(1)}%`, height: '100%', backgroundColor: color }} />
              </View>
              {lane.note ? <Text style={{ color: theme.colors.textFaint, fontSize: 11, marginTop: 6 }}>{lane.note}</Text> : null}
            </View>
          );
        })}
      </View>
    </View>
  );
}
