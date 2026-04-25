import React, { useMemo, useState } from 'react';
import { ScrollView, Text, View, Pressable } from 'react-native';
import { enableNextFamily, launchFamilyDetail, quarantineLaunchFamily, revertLaunchFamily, setLaunchMode } from '../api/launchApi';
import { useCommandCenter } from '../commandCenter/useCommandCenter';
import { FamilyReadinessCard } from '../components/FamilyReadinessCard';
import { LaunchRecommendationCard } from '../components/LaunchRecommendationCard';
import { LAUNCH_WIZARD_STEPS, nextWizardStep, previousWizardStep } from '../state/launchStore';
import { useStore } from '../state/store';
import { useTheme } from '../utils/useTheme';
import { launchWhyNotOverflowCount, launchWhyNotPreview } from '../utils/launch';
import { pageContentContainerStyle, pageShellStyle } from '../utils/layout';
import { SurfaceCard } from '../components/v2/SurfaceCard';
import { HeatMatrixChart } from '../components/v2/charts/HeatMatrixChart';

const MODES = ['V1_ONLY', 'V1_PLUS_STABLE_ALPHA', 'STAGED_MULTI_STRATEGY', 'FULL_MULTI_STRATEGY'] as const;

export function LaunchSetupScreen() {
  const theme = useTheme();
  const cc = useCommandCenter();
  const { state } = useStore();
  const launch = cc.snapshot?.launch;
  const [step, setStep] = useState(0);
  const [detail, setDetail] = useState<string>('');
  const mode = launch?.currentLaunchMode ?? 'V1_ONLY';
  const families = useMemo(() => launch?.families ?? [], [launch]);
  const adminKey = state.role === 'operator' ? state.adminKey : undefined;

  async function selectMode(nextMode: string) {
    await setLaunchMode(state.baseUrl, nextMode, adminKey);
    await cc.refresh();
  }

  async function enableFamily(family: string) {
    await enableNextFamily(state.baseUrl, family, adminKey);
    await cc.refresh();
  }

  async function revertFamily(family: string) {
    await revertLaunchFamily(state.baseUrl, family, adminKey);
    await cc.refresh();
  }

  async function quarantineFamily(family: string) {
    await quarantineLaunchFamily(state.baseUrl, family, 'operator_quarantine', adminKey);
    await cc.refresh();
  }

  async function inspectFamily(family: string) {
    const resp = await launchFamilyDetail(state.baseUrl, family, adminKey);
    const item = (resp as { item?: { blockers?: string[]; reasons?: string[]; suggestedNextAction?: string; degradedState?: string; currentHealthState?: string } }).item;
    setDetail(item ? `Blockers: ${(item.blockers ?? item.reasons ?? []).join(', ') || 'none'} · Next: ${item.suggestedNextAction ?? 'hold'} · State: ${item.currentHealthState ?? item.degradedState ?? 'live'}` : 'No detail available');
  }

  const current = LAUNCH_WIZARD_STEPS[step];
  const focusFamily = launch?.nextRecommendedFamily || launch?.recommendation?.nextFamily || '';
  const heatCells = families.slice(0, 4).map((item) => ({ label: item.family.replace(/_/g, ' '), value: item.score, subtitle: `${item.status} · ${item.currentHealthState ?? item.degradedState ?? 'n/a'}` }));
  const blockedPreview = useMemo(() => launchWhyNotPreview(launch, 3), [launch]);
  const blockedOverflow = useMemo(() => launchWhyNotOverflowCount(launch, 3), [launch]);

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 40)}>
      <Text style={{ color: theme.colors.text, ...theme.typography.title }}>Launch Setup Wizard</Text>
      <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>{current.title} · {current.subtitle}</Text>
      <Text style={{ color: theme.colors.textFaint, marginTop: 6 }}>V1-first is recommended because flash_arb remains the execution truth source for launch expansion.</Text>

      <View style={{ marginTop: 12, flexDirection: 'row', gap: 8 }}>
        {LAUNCH_WIZARD_STEPS.map((entry, idx) => {
          const active = idx === step;
          return <View key={entry.key} style={{ flex: 1, height: 6, borderRadius: 999, backgroundColor: active ? theme.colors.cyan : theme.colors.border }} />;
        })}
      </View>

      {step === 0 ? (
        <SurfaceCard glow="cyan" style={{ marginTop: 12 }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Choose launch mode</Text>
          <View style={{ marginTop: 12, gap: 10 }}>
            {MODES.map((candidate) => (
              <Pressable key={candidate} onPress={() => void selectMode(candidate)} style={{ padding: 14, borderRadius: theme.radii.md, borderWidth: 1, borderColor: candidate === mode ? theme.colors.cyan : theme.colors.border, backgroundColor: candidate === mode ? theme.colors.surface2 : theme.colors.surface1 }}>
                <Text style={{ color: candidate === mode ? theme.colors.text : theme.colors.textMuted, fontWeight: '900' }}>{candidate.replace(/_/g, ' ')}{candidate === mode ? ' · current' : ''}</Text>
              </Pressable>
            ))}
          </View>
        </SurfaceCard>
      ) : null}

      {step === 1 ? (
        <SurfaceCard glow="none" style={{ marginTop: 12 }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Review active families</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Active families: {(launch?.activeFamilies ?? []).join(', ') || 'flash_arb'}</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Recommended next family: {focusFamily ? focusFamily.replace(/_/g, ' ') : 'hold current mode'}</Text>
          {blockedPreview.length ? <Text style={{ color: theme.colors.textFaint, marginTop: 6 }}>Blocked now: {blockedPreview.join(' · ')}</Text> : null}
          {blockedOverflow ? <Text style={{ color: theme.colors.textFaint, marginTop: 4 }}>+{blockedOverflow} more blocked families in rollout detail</Text> : null}
          <View style={{ marginTop: theme.spacing.md }}>
            <HeatMatrixChart cells={heatCells} columns={2} />
          </View>
        </SurfaceCard>
      ) : null}

      {step === 2 ? families.map((item) => (
        <FamilyReadinessCard key={item.family} item={item} onInspect={(family) => void inspectFamily(family)} />
      )) : null}

      {step === 3 ? <LaunchRecommendationCard launch={launch} /> : null}

      {step === 4 ? (
        <SurfaceCard glow="violet" style={{ marginTop: 12 }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Final confirmation</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Mode {mode.replace(/_/g, ' ')} · Next {focusFamily ? focusFamily.replace(/_/g, ' ') : 'none'}</Text>
          {blockedPreview.length ? <Text style={{ color: theme.colors.textFaint, marginTop: 6 }}>Blocked now: {blockedPreview.join(' · ')}</Text> : null}
          <View style={{ gap: 10, marginTop: 12 }}>
            <Pressable onPress={() => void enableFamily(focusFamily)} disabled={!focusFamily} style={{ paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: focusFamily ? theme.colors.cyan : theme.colors.border, alignItems: 'center' }}>
              <Text style={{ color: theme.colors.bg0, fontWeight: '900' }}>Enable recommended family</Text>
            </Pressable>
            {focusFamily ? <Pressable onPress={() => void revertFamily(focusFamily)} style={{ paddingVertical: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1, alignItems: 'center' }}><Text style={{ color: theme.colors.textMuted, fontWeight: '900' }}>Revert to safer mode</Text></Pressable> : null}
            {focusFamily ? <Pressable onPress={() => void quarantineFamily(focusFamily)} style={{ paddingVertical: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.danger, backgroundColor: 'rgba(251, 113, 133, 0.12)', alignItems: 'center' }}><Text style={{ color: theme.colors.danger, fontWeight: '900' }}>Quarantine family</Text></Pressable> : null}
          </View>
        </SurfaceCard>
      ) : null}

      {detail ? <Text style={{ color: theme.colors.textFaint, marginTop: 12 }}>{detail}</Text> : null}

      <View style={{ flexDirection: 'row', gap: 12, marginTop: 16 }}>
        <View style={{ flex: 1 }}>
          <Pressable onPress={() => setStep(previousWizardStep(step))} disabled={step <= 0} style={{ paddingVertical: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: step <= 0 ? theme.colors.surface2 : theme.colors.surface1, alignItems: 'center' }}>
            <Text style={{ color: theme.colors.textMuted, fontWeight: '900' }}>Back</Text>
          </Pressable>
        </View>
        <View style={{ flex: 1 }}>
          <Pressable onPress={() => setStep(nextWizardStep(step))} disabled={step >= LAUNCH_WIZARD_STEPS.length - 1} style={{ paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: step >= LAUNCH_WIZARD_STEPS.length - 1 ? theme.colors.border : theme.colors.cyan, alignItems: 'center' }}>
            <Text style={{ color: theme.colors.bg0, fontWeight: '900' }}>Next</Text>
          </Pressable>
        </View>
      </View>
    </ScrollView>
  );
}
