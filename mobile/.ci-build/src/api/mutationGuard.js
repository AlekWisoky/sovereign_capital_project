"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.mutationKindForSettingsPatch = exports.guardMutation = void 0;
const LIVE_AUTHORITY_MUTATIONS = new Set([
    'enable_live_trading',
    'execution',
    'withdrawal',
]);
/**
 * Client-side safety boundary for operator mutations.
 *
 * This is intentionally fail-closed. It is a UX/security boundary, not a
 * replacement for backend authorization or canonical governance.
 */
function guardMutation(kind, context) {
    if (context.role !== 'operator')
        return { allowed: false, reasonCode: 'operator_required' };
    if (context.locked)
        return { allowed: false, reasonCode: 'operator_locked' };
    if (!context.adminKeyPresent)
        return { allowed: false, reasonCode: 'admin_key_required' };
    if (!context.backendReachable)
        return { allowed: false, reasonCode: 'backend_unavailable' };
    if (LIVE_AUTHORITY_MUTATIONS.has(kind) && !context.backendLiveAuthority) {
        return { allowed: false, reasonCode: 'live_authority_disabled' };
    }
    if (!context.explicitConfirmation) {
        return { allowed: false, reasonCode: 'explicit_confirmation_required' };
    }
    return { allowed: true };
}
exports.guardMutation = guardMutation;
function mutationKindForSettingsPatch(patch) {
    if (patch.auto_trading === true || patch.dry_run === false) {
        return 'enable_live_trading';
    }
    if (patch.auto_trading === false) {
        return 'disable_live_trading';
    }
    return 'settings';
}
exports.mutationKindForSettingsPatch = mutationKindForSettingsPatch;
