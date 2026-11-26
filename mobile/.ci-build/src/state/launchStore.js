"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.sortFamiliesForOperator = exports.chooseFocusedFamily = exports.previousWizardStep = exports.nextWizardStep = exports.LAUNCH_WIZARD_STEPS = exports.DEFAULT_LAUNCH_PREFERENCE = void 0;
exports.DEFAULT_LAUNCH_PREFERENCE = {
    preferredMode: 'V1_ONLY',
    wizardStep: 0,
    focusedFamily: '',
};
exports.LAUNCH_WIZARD_STEPS = [
    { key: 'mode', title: 'Choose launch mode', subtitle: 'Keep V1-first by default and widen only when evidence is stable.' },
    { key: 'active_review', title: 'Review active families', subtitle: 'Confirm current live families and their health posture.' },
    { key: 'readiness', title: 'Inspect readiness and blockers', subtitle: 'Check telemetry, capital, prime, and competition blockers before widening.' },
    { key: 'plan', title: 'Review rollout plan', subtitle: 'See the recommended next family, why now, and why not the others.' },
    { key: 'confirm', title: 'Confirm operator action', subtitle: 'Only activate, pause, revert, or quarantine with a clear reason.' },
];
function nextWizardStep(step) {
    return Math.min(exports.LAUNCH_WIZARD_STEPS.length - 1, Math.max(0, step + 1));
}
exports.nextWizardStep = nextWizardStep;
function previousWizardStep(step) {
    return Math.max(0, step - 1);
}
exports.previousWizardStep = previousWizardStep;
function chooseFocusedFamily(summary) {
    if (!summary)
        return '';
    return summary.nextRecommendedFamily || summary.activeFamilies[0] || summary.families[0]?.family || '';
}
exports.chooseFocusedFamily = chooseFocusedFamily;
function sortFamiliesForOperator(families) {
    return [...families].sort((a, b) => {
        const activeDelta = Number(Boolean(b.active)) - Number(Boolean(a.active));
        if (activeDelta !== 0)
            return activeDelta;
        return (a.rolloutIndex ?? 999) - (b.rolloutIndex ?? 999);
    });
}
exports.sortFamiliesForOperator = sortFamiliesForOperator;
