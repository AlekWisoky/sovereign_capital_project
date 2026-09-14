import React, { useMemo, useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';
import { launchFamilyDetail } from '../api/launchApi';
import { guardedEnableNextFamily, guardedPauseLaunchFamily, guardedQuarantineLaunchFamily, guardedRevertLaunchFamily } from '../api/guardedMutations';
import { guardMutation, type MutationGuardContext } from '../api/mutationGuard';
import { useCommandCenter } from '../commandCenter/useCommandCenter';
import { FamilyReadinessCard } from '../components/FamilyReadinessCard';
import { useStore } from '../state/store';
import { useTheme } from '../utils/useTheme';
import { pageContentContainerStyle, pageShellStyle } from '../utils/layout';
import { SurfaceCard } from '../components/v2/SurfaceCard';
import { HeatMatrixChart } from '../components/v2/charts/HeatMatrixChart';

function confirmMutation(title: string, message: string): Promise<boolean> {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value: boolean) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };
    Alert.alert(
      title,
      message,
      [
        { text: 'Cancel', style: 'cancel', onPress: () => finish(false) },
        { text: 'Confirm', style: 'destructive', onPress: () => finish(true) },
      ],
      { cancelable: true, onDismiss: () => finish(false) },
    );
  });
}

export function FamilyReadinessScreen() {
  const theme = useTheme();
  const cc = useCommandCenter();
  const { state, session } = useStore();
  const adminKey = state.role === 'operator' ? state.adminKey : '';
  const [detail, setDetail] = useState('');

  const families = cc.snapshot?.launch?.families ?? [];
  const matrixCells = useMemo(() => families.map((item) => ({ label: item.family.replace(/_/g, ' '), value: item.score, subtitle: `${item.status} · ${item.riskLevel ?? 'n/a'}` })), [families]);

  function guardContext(explicitConfirmation: boolean): MutationGuardContext {
    return {
      role: state.role === 'operator' ? 'operator' : 'read_only',
      locked: Boolean(session.locked),
      adminKeyPresent: Boolean(state.adminKey?.trim()),
      backendReachable: cc.source === 'backend' && cc.snapshot !== null && !cc.error,
      backendLiveAuthority: false,
      explicitConfirmation,
    };
  }

  async function confirmLaunchAction(action: string): Promise<boolean> {
    const preflight = guardMutation('launch_control', guardContext(false));
    if (!preflight.allowed && preflight.reasonCode !== 'explicit_confirmation_required') {
      setDetail(`Launch control blocked · ${preflight.reasonCode}`);
      return false;
    }
    return confirmMutation('Confirm launch control', `${action}\n\nThis changes backend launch state. Confirm only if this action is intentional.`);
  }

  async function inspectFamily(family: string) {
    const resp = await launchFamilyDetail(state.baseUrl, family, adminKey || undefined);
    const item = (resp as { item?: { blockers?: string[]; reasons?: string[]; suggestedNextAction?: string; degradedState?: string; currentHealthState?: string } }).item;
    setDetail(item ? `${family}: ${(item.blockers ?? item.reasons ?? []).join(', ') || 'no blockers'} · ${item.suggestedNextAction ?? 'hold'} · ${item.currentHealthState ?? item.degradedState ?? 'live'}` : 'No detail available');
  }

  async function pauseFamily(family: string) {
    if (!(await confirmLaunchAction(`Pause launch family ${family}?`))) return;
    try {
      await guardedPauseLaunchFamily(state.baseUrl, family, adminKey, guardContext(true));
      await cc.refresh();
    } catch (error: unknown) {
      setDetail(error instanceof Error ? error.message : String(error));
    }
  }

  async function revertFamily(family: string) {
    if (!(await confirmLaunchAction(`Revert launch family ${family} to the safer state?`))) return;
    try {
      await guardedRevertLaunchFamily(state.baseUrl, family, adminKey, guardContext(true));
      await cc.refresh();
    } catch (error: unknown) {
      setDetail(error instanceof Error ? error.message : String(error));
    }
  }

  async function quarantineFamily(family: string) {
    if (!(await confirmLaunchAction(`Quarantine launch family ${family}?`))) return;
    try {
      await guardedQuarantineLaunchFamily(state.baseUrl, family, adminKey, guardContext(true), 'operator_quarantine');
      await cc.refresh();
    } catch (error: unknown) {
      setDetail(error instanceof Error ? error.message : String(error));
    }
  }

  async function enableFamily(family: string) {
    if (!family) return;
    if (!(await confirmLaunchAction(`Enable launch family ${family}?`))) return;
    try {
      await guardedEnableNextFamily(state.baseUrl, family, adminKey, guardContext(true));
      await cc.refresh();
    } catch (error: unknown) {
      setDetail(error instanceof Error ? error.message : String(error));
    }
  }

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 40)}>
      <Text style={{ color: theme.colors.text, ...theme.typography.title }}>Family Readiness</Text>
      <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Inspect readiness, blockers, degraded states, and rollback actions family by family.</Text>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="cyan">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Readiness Heat Grid</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Structured operator view across readiness, scale posture, and risk semantics.</Text>
        <View style={{ marginTop: theme.spacing.md }}>
          <HeatMatrixChart cells={matrixCells} columns={2} />
        </View>
      </SurfaceCard>

      {(families ?? []).map((item) => (
        <FamilyReadinessCard
          key={item.family}
          item={item}
          onInspect={(family) => void inspectFamily(family)}
          onEnable={(family) => void enableFamily(family)}
          onPause={(family) => void pauseFamily(family)}
          onRevert={(family) => void revertFamily(family)}
          onQuarantine={(family) => void quarantineFamily(family)}
        />
      ))}
      {detail ? <Text style={{ color: theme.colors.textFaint, marginTop: 12 }}>{detail}</Text> : null}
    </ScrollView>
  );
}