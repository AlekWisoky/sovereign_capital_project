"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_fs_1 = __importDefault(require("node:fs"));
const node_path_1 = __importDefault(require("node:path"));
const node_test_1 = __importDefault(require("node:test"));
const mutationGuard_1 = require("../src/api/mutationGuard");
const base = {
    role: 'operator',
    locked: false,
    adminKeyPresent: true,
    backendReachable: true,
    backendLiveAuthority: false,
    explicitConfirmation: true,
};
(0, node_test_1.default)('read-only users cannot mutate', () => {
    const result = (0, mutationGuard_1.guardMutation)('settings', { ...base, role: 'read_only' });
    strict_1.default.deepEqual(result, { allowed: false, reasonCode: 'operator_required' });
});
(0, node_test_1.default)('locked operator cannot mutate', () => {
    const result = (0, mutationGuard_1.guardMutation)('settings', { ...base, locked: true });
    strict_1.default.deepEqual(result, { allowed: false, reasonCode: 'operator_locked' });
});
(0, node_test_1.default)('missing admin key fails closed', () => {
    const result = (0, mutationGuard_1.guardMutation)('settings', { ...base, adminKeyPresent: false });
    strict_1.default.deepEqual(result, { allowed: false, reasonCode: 'admin_key_required' });
});
(0, node_test_1.default)('unreachable backend fails closed', () => {
    const result = (0, mutationGuard_1.guardMutation)('settings', { ...base, backendReachable: false });
    strict_1.default.deepEqual(result, { allowed: false, reasonCode: 'backend_unavailable' });
});
(0, node_test_1.default)('capital execution remains blocked until backend live authority exists', () => {
    const result = (0, mutationGuard_1.guardMutation)('execution', base);
    strict_1.default.deepEqual(result, { allowed: false, reasonCode: 'live_authority_disabled' });
});
(0, node_test_1.default)('enabling live trading remains blocked until backend live authority exists', () => {
    const result = (0, mutationGuard_1.guardMutation)('enable_live_trading', base);
    strict_1.default.deepEqual(result, { allowed: false, reasonCode: 'live_authority_disabled' });
});
(0, node_test_1.default)('disabling live trading is allowed only after explicit confirmation', () => {
    const denied = (0, mutationGuard_1.guardMutation)('disable_live_trading', { ...base, explicitConfirmation: false });
    strict_1.default.deepEqual(denied, { allowed: false, reasonCode: 'explicit_confirmation_required' });
    const allowed = (0, mutationGuard_1.guardMutation)('disable_live_trading', base);
    strict_1.default.deepEqual(allowed, { allowed: true });
});
(0, node_test_1.default)('all backend operator mutation classes require explicit confirmation', () => {
    for (const kind of ['settings', 'chain_control', 'launch_control', 'disable_live_trading']) {
        const denied = (0, mutationGuard_1.guardMutation)(kind, { ...base, explicitConfirmation: false });
        strict_1.default.deepEqual(denied, { allowed: false, reasonCode: 'explicit_confirmation_required' }, kind);
        strict_1.default.deepEqual((0, mutationGuard_1.guardMutation)(kind, base), { allowed: true }, kind);
    }
});
(0, node_test_1.default)('ordinary settings require explicit confirmation', () => {
    const result = (0, mutationGuard_1.guardMutation)('settings', { ...base, explicitConfirmation: false });
    strict_1.default.deepEqual(result, { allowed: false, reasonCode: 'explicit_confirmation_required' });
});
(0, node_test_1.default)('settings classification treats activation-shaped patches as live authority changes', () => {
    strict_1.default.equal((0, mutationGuard_1.mutationKindForSettingsPatch)({ auto_trading: true }), 'enable_live_trading');
    strict_1.default.equal((0, mutationGuard_1.mutationKindForSettingsPatch)({ dry_run: false }), 'enable_live_trading');
    strict_1.default.equal((0, mutationGuard_1.mutationKindForSettingsPatch)({ auto_trading: false }), 'disable_live_trading');
    strict_1.default.equal((0, mutationGuard_1.mutationKindForSettingsPatch)({ send_mode: 'private' }), 'settings');
});
const ACTIVE_OPERATOR_SCREENS = [
    'v2/DashScreen.tsx',
    'v2/SetupScreen.tsx',
    'v2/TrackerScreen.tsx',
    'v2/WalletScreen.tsx',
    'cc/OffRampScreen.tsx',
    'cc/HomeCommandScreen.tsx',
    'FamilyReadinessScreen.tsx',
    'LaunchSetupScreen.tsx',
];
const RAW_MUTATION_NAMES = [
    'setSettings',
    'setWealthGoal',
    'tradeOpportunity',
    'withdrawExecute',
    'withdrawAllExecute',
    'convertWithdrawExecute',
    'saveRpcPreferences',
    'setLaunchMode',
    'applyPreset',
    'selectChain',
    'selectActiveChain',
    'enableNextFamily',
    'pauseLaunchFamily',
    'revertLaunchFamily',
    'quarantineLaunchFamily',
];
function readOperatorScreen(relativePath) {
    const filePath = node_path_1.default.resolve(__dirname, '../../src/screens', relativePath);
    return node_fs_1.default.readFileSync(filePath, 'utf8');
}
(0, node_test_1.default)('active operator screens do not import raw backend mutation APIs', () => {
    for (const relativePath of ACTIVE_OPERATOR_SCREENS) {
        const source = readOperatorScreen(relativePath);
        for (const name of RAW_MUTATION_NAMES) {
            const rawImport = new RegExp(`(?:import|require)[^\\n]*\\b${name}\\b[^\\n]*api/client`);
            strict_1.default.equal(rawImport.test(source), false, `${relativePath} imports raw mutation ${name}`);
        }
    }
});
(0, node_test_1.default)('active operator screens do not invoke raw backend mutation APIs', () => {
    for (const relativePath of ACTIVE_OPERATOR_SCREENS) {
        const source = readOperatorScreen(relativePath);
        for (const name of RAW_MUTATION_NAMES) {
            const rawInvocation = new RegExp(`\\b${name}\\s*\\(`);
            strict_1.default.equal(rawInvocation.test(source), false, `${relativePath} invokes raw mutation ${name}`);
        }
    }
});
(0, node_test_1.default)('guarded mutation boundary is present for every migrated operator screen', () => {
    for (const relativePath of ACTIVE_OPERATOR_SCREENS) {
        const source = readOperatorScreen(relativePath);
        strict_1.default.match(source, /guarded[A-Za-z]+\(/, `${relativePath} must call a guarded adapter`);
    }
});
(0, node_test_1.default)('store chain mutation uses the guarded boundary and never calls raw selectChain', () => {
    const source = node_fs_1.default.readFileSync(node_path_1.default.resolve(__dirname, '../../src/state/store.tsx'), 'utf8');
    strict_1.default.doesNotMatch(source, /import[^\n]*\bselectChain\b[^\n]*api\/client/);
    strict_1.default.match(source, /guardedSelectChain\(/);
    strict_1.default.match(source, /guardMutation\('chain_control'/);
    strict_1.default.match(source, /explicitConfirmation/);
});
(0, node_test_1.default)('Setup preserves backend URL wiring and premium RPC preference fields', () => {
    const source = readOperatorScreen('v2/SetupScreen.tsx');
    strict_1.default.match(source, /Backend base URL/);
    strict_1.default.match(source, /health\(safeBaseUrl/);
    strict_1.default.match(source, /deployInfo\(safeBaseUrl/);
    strict_1.default.match(source, /guardedSaveRpcPreferences\(/);
    strict_1.default.match(source, /Premium read RPCs/);
    strict_1.default.match(source, /Premium send RPCs/);
    strict_1.default.match(source, /Premium private \/ bundle RPCs/);
});
(0, node_test_1.default)('Setup backend synchronization is explicit and keeps live authority disabled', () => {
    const source = readOperatorScreen('v2/SetupScreen.tsx');
    strict_1.default.match(source, /Confirm backend synchronization/);
    strict_1.default.match(source, /backendLiveAuthority: false/);
    strict_1.default.match(source, /if \(!\(await confirmBackendSync\(\)\)\)/);
    strict_1.default.match(source, /guardedApplyPreset\(/);
});
