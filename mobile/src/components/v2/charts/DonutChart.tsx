import React, { useMemo } from 'react';
import { View, Text } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { useTheme } from '../../../utils/useTheme';

type Slice = { label: string; value: number; color?: string };

function polar(cx: number, cy: number, r: number, angle: number) {
  return {
    x: cx + r * Math.cos((angle - 90) * Math.PI / 180),
    y: cy + r * Math.sin((angle - 90) * Math.PI / 180),
  };
}

export function DonutChart({ size = 164, thickness = 16, slices, centerLabel, centerValue }: { size?: number; thickness?: number; slices: Slice[]; centerLabel?: string; centerValue?: string }) {
  const theme = useTheme();
  const radius = (size - thickness) / 2;
  const cx = size / 2;
  const cy = size / 2;

  const normalized = useMemo(() => {
    const safe = slices.map((item, idx) => ({
      ...item,
      value: Number.isFinite(item.value) ? Math.max(0, item.value) : 0,
      color: item.color ?? [theme.colors.cyan, theme.colors.violet, theme.colors.good, theme.colors.warn, theme.colors.danger][idx % 5],
    }));
    const total = safe.reduce((sum, item) => sum + item.value, 0);
    return { total: total || 1, slices: safe };
  }, [slices, theme]);

  let cursor = 0;
  return (
    <View style={{ alignItems: 'center', justifyContent: 'center' }}>
      <Svg width={size} height={size}>
        <Circle cx={cx} cy={cy} r={radius} stroke={theme.colors.border} strokeWidth={thickness} fill="none" opacity={0.35} />
        {normalized.slices.map((slice, idx) => {
          const pct = slice.value / normalized.total;
          const circumference = 2 * Math.PI * radius;
          const dash = circumference * pct;
          const gap = circumference - dash;
          const rotate = cursor * 360;
          cursor += pct;
          return (
            <Circle
              key={`${slice.label}-${idx}`}
              cx={cx}
              cy={cy}
              r={radius}
              stroke={slice.color}
              strokeWidth={thickness}
              strokeLinecap="round"
              fill="none"
              strokeDasharray={`${dash} ${gap}`}
              transform={`rotate(${rotate} ${cx} ${cy})`}
            />
          );
        })}
      </Svg>
      <View style={{ position: 'absolute', alignItems: 'center', justifyContent: 'center' }}>
        {centerLabel ? <Text style={{ color: theme.colors.textFaint, fontSize: 11, fontWeight: '700' }}>{centerLabel}</Text> : null}
        {centerValue ? <Text style={{ color: theme.colors.text, fontSize: 18, fontWeight: '900', marginTop: 4 }}>{centerValue}</Text> : null}
      </View>
      <View style={{ width: '100%', marginTop: 10, gap: 8 }}>
        {normalized.slices.map((slice, idx) => (
          <View key={`${slice.label}-legend-${idx}`} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1, paddingRight: 12 }}>
              <View style={{ width: 10, height: 10, borderRadius: 999, backgroundColor: slice.color }} />
              <Text style={{ color: theme.colors.textMuted, fontSize: 12, fontWeight: '700' }}>{slice.label}</Text>
            </View>
            <Text style={{ color: theme.colors.text, fontSize: 12, fontWeight: '800' }}>{slice.value.toFixed(1)}%</Text>
          </View>
        ))}
      </View>
    </View>
  );
}
