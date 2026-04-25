import React from 'react';
import { Pressable, Text, View } from 'react-native';
import type { FamilyReadiness } from '../commandCenter/types';
import { useTheme } from '../utils/useTheme';
import { familyDependencyRows, launchStatusLabel } from '../utils/launch';

function pillTone(status: FamilyReadiness['status'], theme: ReturnType<typeof useTheme>) {
  if (status === 'eligible') return { bg: 'rgba(52, 211, 153, 0.14)', border: theme.colors.good, text: theme.colors.good };
  if (status === 'degraded') return { bg: 'rgba(251, 191, 36, 0.14)', border: theme.colors.warn, text: theme.colors.warn };
  if (status === 'quarantined') return { bg: 'rgba(251, 113, 133, 0.14)', border: theme.colors.danger, text: theme.colors.danger };
  return { bg: theme.colors.surface2, border: theme.colors.border, text: theme.colors.textMuted };
}

export function FamilyReadinessCard({
  item,
  onEnable,
  onPause,
  onRevert,
  onQuarantine,
  onInspect,
}: {
  item: FamilyReadiness;
  onEnable?: (family: string) => void;
  onPause?: (family: string) => void;
  onRevert?: (family: string) => void;
  onQuarantine?: (family: string) => void;
  onInspect?: (family: string) => void;
}) {
  const theme = useTheme();
  const deps = familyDependencyRows(item);
  const tone = pillTone(item.status, theme);
  const readinessPct = item.score * 100;
  const successPct = item.successRate * 100;
  const routePct = (item.routeReliability ?? item.calibrationQuality) * 100;
  const venuePct = (item.venueReliability ?? item.calibrationQuality) * 100;
  return (
    <View style={{ padding: 14, borderRadius: theme.radii.lg, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1, marginTop: 12 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ color: theme.colors.text, fontWeight: '900', fontSize: 16 }}>{item.family.replace(/_/g, ' ')}</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 4, fontSize: 12 }}>{launchStatusLabel(item)}</Text>
        </View>
        <View style={{ paddingVertical: 6, paddingHorizontal: 10, borderRadius: theme.radii.pill, borderWidth: 1, borderColor: tone.border, backgroundColor: tone.bg }}>
          <Text style={{ color: tone.text, fontSize: 12, fontWeight: '900' }}>{item.status.toUpperCase()}</Text>
        </View>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 12 }}>
        {[
          ['Readiness', `${readinessPct.toFixed(0)}%`],
          ['Success', `${successPct.toFixed(0)}%`],
          ['Route', `${routePct.toFixed(0)}%`],
          ['Venue', `${venuePct.toFixed(0)}%`],
          ['Capital', item.capitalReady ? 'ready' : 'hold'],
          ['Prime', item.internalPrimeReady ? 'ready' : 'hold'],
        ].map(([label, value]) => (
          <View key={label} style={{ minWidth: 92, flexGrow: 1, padding: 10, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface2 }}>
            <Text style={{ color: theme.colors.textFaint, fontSize: 11, fontWeight: '700' }}>{label}</Text>
            <Text style={{ color: theme.colors.text, marginTop: 4, fontSize: 14, fontWeight: '900' }}>{value}</Text>
          </View>
        ))}
      </View>

      <Text style={{ color: theme.colors.textFaint, marginTop: 10, fontSize: 12 }}>Dependencies: {deps.map((dep) => `${dep.label}:${dep.ok ? 'ok' : 'hold'}`).join(' · ')}</Text>
      <Text style={{ color: theme.colors.textFaint, marginTop: 4, fontSize: 12 }}>Risk {String(item.riskLevel ?? 'low')} · Competition {(((item.competitionPressure ?? 0) as number) * 100).toFixed(0)}% · Health {String(item.currentHealthState ?? item.degradedState ?? 'n/a')}</Text>
      {!!item.suggestedNextAction ? <Text style={{ color: theme.colors.textMuted, marginTop: 8, fontSize: 12 }}>Suggested next action: {String(item.suggestedNextAction).replace(/_/g, ' ')}</Text> : null}
      {!!item.blockers?.length ? <Text style={{ color: theme.colors.warn, marginTop: 8, fontSize: 12 }}>Blockers: {item.blockers.join(' · ')}</Text> : null}

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 12 }}>
        {onInspect ? <ActionButton title="Inspect" tone="neutral" onPress={() => onInspect(item.family)} /> : null}
        {!item.active && onEnable ? <ActionButton title="Promote" tone="primary" disabled={!item.ready} onPress={() => onEnable(item.family)} /> : null}
        {item.active && onPause ? <ActionButton title="Pause" tone="neutral" onPress={() => onPause(item.family)} /> : null}
        {onRevert ? <ActionButton title="Safer Mode" tone="neutral" onPress={() => onRevert(item.family)} /> : null}
        {onQuarantine ? <ActionButton title="Quarantine" tone="danger" onPress={() => onQuarantine(item.family)} /> : null}
      </View>
    </View>
  );
}

function ActionButton({ title, onPress, tone, disabled }: { title: string; onPress: () => void; tone: 'primary' | 'neutral' | 'danger'; disabled?: boolean }) {
  const theme = useTheme();
  const bg = disabled ? theme.colors.border : tone === 'primary' ? theme.colors.cyan : tone === 'danger' ? 'rgba(251, 113, 133, 0.12)' : theme.colors.surface2;
  const color = disabled ? theme.colors.textFaint : tone === 'primary' ? theme.colors.bg0 : tone === 'danger' ? theme.colors.danger : theme.colors.textMuted;
  const borderColor = tone === 'danger' ? theme.colors.danger : tone === 'primary' ? theme.colors.cyan : theme.colors.border;
  return (
    <Pressable disabled={disabled} onPress={onPress} style={{ paddingVertical: 10, paddingHorizontal: 12, borderRadius: 999, borderWidth: 1, borderColor, backgroundColor: bg }}>
      <Text style={{ color, fontSize: 12, fontWeight: '900' }}>{title}</Text>
    </Pressable>
  );
}
