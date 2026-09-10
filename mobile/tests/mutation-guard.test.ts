import assert from 'node:assert/strict';
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
