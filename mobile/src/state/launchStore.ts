import type { FamilyReadiness, LaunchMode, LaunchSummary } from '../commandCenter/types';

export type LaunchPreference = {
  preferredMode: LaunchMode;
  wizardStep: number;
  focusedFamily: string;
};

export type LaunchWizardStep = {
  key: 'mode' | 'active_review' | 'readiness' | 'plan' | 'confirm';
  title: string;
  subtitle: string;
};

export const DEFAULT_LAUNCH_PREFERENCE: LaunchPreference = {
  preferredMode: 'V1_ONLY',
  wizardStep: 0,
  focusedFamily: '',
};

export const LAUNCH_WIZARD_STEPS: LaunchWizardStep[] = [
  { key: 'mode', title: 'Choose launch mode', subtitle: 'Keep V1-first by default and widen only when evidence is stable.' },
  { key: 'active_review', title: 'Review active families', subtitle: 'Confirm current live families and their health posture.' },
  { key: 'readiness', title: 'Inspect readiness and blockers', subtitle: 'Check telemetry, capital, prime, and competition blockers before widening.' },
  { key: 'plan', title: 'Review rollout plan', subtitle: 'See the recommended next family, why now, and why not the others.' },
  { key: 'confirm', title: 'Confirm operator action', subtitle: 'Only activate, pause, revert, or quarantine with a clear reason.' },
];

export function nextWizardStep(step: number): number {
  return Math.min(LAUNCH_WIZARD_STEPS.length - 1, Math.max(0, step + 1));
}

export function previousWizardStep(step: number): number {
  return Math.max(0, step - 1);
}

export function chooseFocusedFamily(summary?: LaunchSummary | null): string {
  if (!summary) return '';
  return summary.nextRecommendedFamily || summary.activeFamilies[0] || summary.families[0]?.family || '';
}

export function sortFamiliesForOperator(families: FamilyReadiness[]): FamilyReadiness[] {
  return [...families].sort((a, b) => {
    const activeDelta = Number(Boolean(b.active)) - Number(Boolean(a.active));
    if (activeDelta !== 0) return activeDelta;
    return (a.rolloutIndex ?? 999) - (b.rolloutIndex ?? 999);
  });
}
