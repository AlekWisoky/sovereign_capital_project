import React from 'react';
import { View, Text } from 'react-native';
import { useTheme } from '../../../utils/useTheme';

type Cell = { label: string; value: number; subtitle?: string };

function tone(value: number, theme: ReturnType<typeof useTheme>) {
  if (value >= 0.8) return { bg: 'rgba(52, 211, 153, 0.18)', border: theme.colors.good, text: theme.colors.good };
  if (value >= 0.55) return { bg: 'rgba(251, 191, 36, 0.16)', border: theme.colors.warn, text: theme.colors.warn };
  return { bg: 'rgba(251, 113, 133, 0.16)', border: theme.colors.danger, text: theme.colors.danger };
}

export function HeatMatrixChart({ title, cells, columns = 2 }: { title?: string; cells: Cell[]; columns?: number }) {
  const theme = useTheme();
  return (
    <View>
      {title ? <Text style={{ color: theme.colors.textMuted, fontSize: 12, fontWeight: '800', marginBottom: 10 }}>{title}</Text> : null}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginHorizontal: -5 }}>
        {cells.map((cell) => {
          const t = tone(cell.value, theme);
          return (
            <View key={cell.label} style={{ width: `${100 / columns}%`, paddingHorizontal: 5, marginBottom: 10 }}>
              <View style={{ borderRadius: theme.radii.md, borderWidth: 1, borderColor: t.border, backgroundColor: t.bg, padding: 12, minHeight: 84 }}>
                <Text style={{ color: theme.colors.text, fontWeight: '800', fontSize: 12 }}>{cell.label}</Text>
                <Text style={{ color: t.text, fontWeight: '900', fontSize: 22, marginTop: 6 }}>{Math.round(cell.value * 100)}%</Text>
                {cell.subtitle ? <Text style={{ color: theme.colors.textFaint, fontSize: 11, marginTop: 6 }}>{cell.subtitle}</Text> : null}
              </View>
            </View>
          );
        })}
      </View>
    </View>
  );
}
