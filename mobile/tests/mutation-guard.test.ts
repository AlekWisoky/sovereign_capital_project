import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { guardMutation, mutationKindForSettingsPatch, type MutationGuardContext } from '../src/api/mutationGuard';

const base: MutationGuardContext = {
  role: 'operator',
  locked: false,
  adminKeyPresent: true,
  backendReachable: true,
  backendLiveAuthority: false,
  explicitConfirmation: true,
};

test('read-only users cannot mutate', () => {
  const result = guardMutation('settings', { ...base, role: 'read_only' });
  assert.deepEqual(result, { allowed: false, reasonCode: 'operator_required' });
});

test('locked operator cannot mutate', () => {
  const result = guardMutation('settings', { ...base, locked: true });
  assert.deepEqual(result, { allowed: false, reasonCode: 'operator_locked' });
});

test('missing admin key fails closed', () => {
  const result = guardMutation('settings', { ...base, adminKeyPresent: false });
  assert.deepEqual(result, { allowed: false, reasonCode: 'admin_key_required' });
});

test('unreachable backend fails closed', () => {
  const result = guardMutation('settings', { ...base, backendReachable: false });
  assert.deepEqual(result, { allowed: false, reasonCode: 'backend_unavailable' });
});

test('capital execution remains blocked until backend live authority exists', () => {
  const result = guardMutation('execution', base);
  assert.deepEqual(result, { allowed: false, reasonCode: 'live_authority_disabled' });
});

test('enabling live trading remains blocked until backend live authority exists', () => {
  const result = guardMutation('enable_live_trading', base);
  assert.deepEqual(result, { allowed: false, reasonCode: 'live_authority_disabled' });
});

test('disabling live trading is allowed only after explicit confirmation', () => {
  const denied = guardMutation('disable_live_trading', { ...base, explicitConfirmation: false });
  assert.deepEqual(denied, { allowed: false, reasonCode: 'explicit_confirmation_required' });

  const allowed = guardMutation('disable_live_trading', base);
  assert.deepEqual(allowed, { allowed: true });
});

test('all backend operator mutation classes require explicit confirmation', () => {
  for (const kind of ['settings', 'chain_control', 'launch_control', 'disable_live_trading'] as const) {
    const denied = guardMutation(kind, { ...base, explicitConfirmation: false });
    assert.deepEqual(denied, { allowed: false, reasonCode: 'explicit_confirmation_required' }, kind);
    assert.deepEqual(guardMutation(kind, base), { allowed: true }, kind);
  }
});

test('ordinary settings require explicit confirmation', () => {
  const result = guardMutation('settings', { ...base, explicitConfirmation: false });
  assert.deepEqual(result, { allowed: false, reasonCode: 'explicit_confirmation_required' });
});

test('settings classification treats activation-shaped patches as live authority changes', () => {
  assert.equal(mutationKindForSettingsPatch({ auto_trading: true }), 'enable_live_trading');
  assert.equal(mutationKindForSettingsPatch({ dry_run: false }), 'enable_live_trading');
  assert.equal(mutationKindForSettingsPatch({ auto_trading: false }), 'disable_live_trading');
  assert.equal(mutationKindForSettingsPatch({ send_mode: 'private' }), 'settings');
});

const ACTIVE_OPERATOR_SCREENS = [
  'v2/DashScreen.tsx',
  'v2/SetupScreen.tsx',
  'v2/TrackerScreen.tsx',
  'v2/WalletScreen.tsx',
  'cc/OffRampScreen.tsx',
  'LaunchSetupScreen.tsx',
] as const;

const RAW_MUTATION_NAMES = [
  'setSettings',
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
] as const;

function readOperatorScreen(relativePath: string): string {
  const filePath = path.resolve(__dirname, '../../src/screens', relativePath);
  return fs.readFileSync(filePath, 'utf8');
}

test('active operator screens do not import raw backend mutation APIs', () => {
  for (const relativePath of ACTIVE_OPERATOR_SCREENS) {
    const source = readOperatorScreen(relativePath);
    for (const name of RAW_MUTATION_NAMES) {
      const rawImport = new RegExp(`(?:import|require)[^\\n]*\\b${name}\\b[^\\n]*api/client`);
      assert.equal(rawImport.test(source), false, `${relativePath} imports raw mutation ${name}`);
    }
  }
});

test('active operator screens do not invoke raw backend mutation APIs', () => {
  for (const relativePath of ACTIVE_OPERATOR_SCREENS) {
    const source = readOperatorScreen(relativePath);
    for (const name of RAW_MUTATION_NAMES) {
      const rawInvocation = new RegExp(`\\b${name}\\s*\\(`);
      assert.equal(rawInvocation.test(source), false, `${relativePath} invokes raw mutation ${name}`);
    }
  }
});

test('guarded mutation boundary is present for every migrated operator screen', () => {
  for (const relativePath of ACTIVE_OPERATOR_SCREENS) {
    const source = readOperatorScreen(relativePath);
    assert.match(source, /guarded[A-Za-z]+\(/, `${relativePath} must call a guarded adapter`);
  }
});

test('Setup preserves backend URL wiring and premium RPC preference fields', () => {
  const source = readOperatorScreen('v2/SetupScreen.tsx');
  assert.match(source, /Backend base URL/);
  assert.match(source, /health\(safeBaseUrl/);
  assert.match(source, /deployInfo\(safeBaseUrl/);
  assert.match(source, /guardedSaveRpcPreferences\(/);
  assert.match(source, /Premium read RPCs/);
  assert.match(source, /Premium send RPCs/);
  assert.match(source, /Premium private \/ bundle RPCs/);
});

test('Setup backend synchronization is explicit and keeps live authority disabled', () => {
  const source = readOperatorScreen('v2/SetupScreen.tsx');
  assert.match(source, /Confirm backend synchronization/);
  assert.match(source, /backendLiveAuthority: false/);
  assert.match(source, /if \(!\(await confirmBackendSync\(\)\)\)/);
  assert.match(source, /guardedApplyPreset\(/);
});
