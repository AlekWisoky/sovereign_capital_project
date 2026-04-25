import React from 'react';
import { View, Text } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { useTheme } from '../../../utils/useTheme';

export function RadialGauge({ value, max = 100, size = 168, label, subtitle, tone }: { value: number; max?: number; size?: number; label?: string; subtitle?: string; tone?: 'good' | 'warn' | 'danger' | 'cyan' | 'violet' }) {
  const theme = useTheme();
  const pct = Math.max(0, Math.min(1, value / (max || 100)));
  const stroke = tone === 'good' ? theme.colors.good : tone === 'warn' ? theme.colors.warn : tone === 'danger' ? theme.colors.danger : tone === 'violet' ? theme.colors.violet : theme.colors.cyan;
  const thickness = 14;
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  const dash = circumference * pct;
  const gap = circumference - dash;
  const cx = size / 2;
  const cy = size / 2;

  return (
    <View style={{ alignItems: 'center', justifyContent: 'center' }}>
      <Svg width={size} height={size}>
        <Circle cx={cx} cy={cy} r={radius} stroke={theme.colors.border} strokeWidth={thickness} fill="none" opacity={0.35} />
        <Circle cx={cx} cy={cy} r={radius} stroke={stroke} strokeWidth={thickness} fill="none" strokeLinecap="round" strokeDasharray={`${dash} ${gap}`} transform={`rotate(-90 ${cx} ${cy})`} />
      </Svg>
      <View style={{ position: 'absolute', alignItems: 'center' }}>
        {label ? <Text style={{ color: theme.colors.textFaint, fontSize: 11, fontWeight: '700' }}>{label}</Text> : null}
        <Text style={{ color: theme.colors.text, fontSize: 26, fontWeight: '900', marginTop: 4 }}>{Math.round(value)}</Text>
        {subtitle ? <Text style={{ color: theme.colors.textMuted, fontSize: 12, fontWeight: '700', marginTop: 4 }}>{subtitle}</Text> : null}
      </View>
    </View>
  );
}
