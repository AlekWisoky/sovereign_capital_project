import test from 'node:test';
import { strict as assert } from 'node:assert';
import { describeWithdrawAllRefresh, describeWithdrawAllRefreshWarning, nextWithdrawAllRefreshDelayMs, shouldAutoRefreshWithdrawAllState, summarizeWithdrawExecution, summarizeWithdrawAllExecution, summarizeWithdrawAllState } from '../src/utils/offRampStatus';

test('summarizeWithdrawExecution reports pending submission without claiming completion', () => {
  const summary = summarizeWithdrawExecution({ ok: true, status: 'pending', tx_hash: '0x' + '1'.repeat(64) }, 'Withdraw');
  assert.equal(summary.headline, 'Withdraw pending');
  assert.match(summary.detail, /pending confirmation/i);
});

test('summarizeWithdrawExecution reports read-rpc visibility proof for pending txs', () => {
  const summary = summarizeWithdrawExecution({ ok: true, status: 'pending', tx_proof_reason: 'tx_visible', tx_hash: '0x' + '4'.repeat(64) }, 'Withdraw');
  assert.equal(summary.headline, 'Withdraw pending');
  assert.match(summary.detail, /visible on the read RPC/i);
});

test('summarizeWithdrawExecution distinguishes degraded receipt lookup from generic receipt unavailability', () => {
  const summary = summarizeWithdrawExecution({ ok: true, status: 'receipt_unavailable', tx_proof_reason: 'receipt_lookup_degraded', tx_hash: '0x' + '5'.repeat(64) }, 'Convert+withdraw');
  assert.equal(summary.headline, 'Convert+withdraw receipt unavailable');
  assert.match(summary.detail, /receipt lookup on the read RPC degraded/i);
});

test('summarizeWithdrawExecution distinguishes private submission from generic sent status', () => {
  const summary = summarizeWithdrawExecution({ ok: true, status: 'sent', tx_proof_reason: 'private_no_public_receipt', tx_hash: '0x' + '6'.repeat(64) }, 'Withdraw');
  assert.equal(summary.headline, 'Withdraw sent');
  assert.match(summary.detail, /private submission/i);
});

test('summarizeWithdrawExecution reports on-chain revert as failure', () => {
  const summary = summarizeWithdrawExecution({ ok: false, reason_code: 'receipt_reverted', tx_hash: '0x' + '2'.repeat(64) }, 'Convert+withdraw');
  assert.equal(summary.ok, false);
  assert.equal(summary.status, 'receipt_reverted');
  assert.match(summary.detail, /reverted on-chain/i);
});

test('summarizeWithdrawAllExecution distinguishes submitted from completed', () => {
  const summary = summarizeWithdrawAllExecution({ ok: true, result: { status: 'submitted', submission_state: 'sent' } });
  assert.equal(summary.headline, 'Wipe sent');
  assert.match(summary.detail, /not visible yet/i);
});



test('summarizeWithdrawAllExecution uses read-rpc visibility proof for pending wipe submissions', () => {
  const summary = summarizeWithdrawAllExecution({ ok: true, result: { status: 'submitted', submission_state: 'pending', submission_proof_reason: 'tx_visible' } });
  assert.equal(summary.headline, 'Wipe pending');
  assert.match(summary.detail, /visible on the read RPC/i);
});

test('summarizeWithdrawAllExecution distinguishes private submission from generic sent wipe status', () => {
  const summary = summarizeWithdrawAllExecution({ ok: true, result: { status: 'submitted', submission_state: 'sent', submission_proof_reason: 'private_no_public_receipt' } });
  assert.equal(summary.headline, 'Wipe sent');
  assert.match(summary.detail, /private submission/i);
});

test('summarizeWithdrawAllState surfaces failed last execution from persisted state', () => {
  const summary = summarizeWithdrawAllState({
    last_status: 'execute_failed',
    last_reason_code: 'receipt_reverted',
    last_result: { failed_item: { tx_hash: '0x' + '3'.repeat(64) } },
  });
  assert.equal(summary !== null, true);
  assert.equal(summary?.headline, 'Wipe failed');
  assert.match(String(summary?.detail), /reverted on-chain/i);
});

test('summarizeWithdrawAllState includes item-level lifecycle counts from persisted state', () => {
  const summary = summarizeWithdrawAllState({
    last_status: 'submitted',
    last_reason_code: 'ok',
    last_result: { status: 'submitted', submission_state: 'mixed' },
    last_result_summary: {
      status: 'submitted',
      reason_code: 'ok',
      submission_state: 'mixed',
      attempted_item_count: 3,
      confirmed_item_count: 1,
      outstanding_item_count: 2,
      reverted_item_count: 0,
      failed_item_count: 0,
      item_status_counts: { mined_success: 1, pending: 2 },
    },
  });
  assert.equal(summary !== null, true);
  assert.equal(summary?.headline, 'Wipe submitted');
  assert.match(String(summary?.detail), /1 item confirmed/i);
  assert.match(String(summary?.detail), /2 items awaiting confirmation/i);
});

test('summarizeWithdrawAllState surfaces blocked control state before any wipe execution exists', () => {
  const summary = summarizeWithdrawAllState({
    status: 'blocked',
    reason_code: 'approved_destination_missing',
    control_reason_code: 'approved_destination_missing',
    last_status: 'idle',
  });
  assert.equal(summary !== null, true);
  assert.equal(summary?.headline, 'Wipe blocked');
  assert.match(String(summary?.detail), /blocked until an approved destination is configured/i);
});

test('summarizeWithdrawAllState surfaces degraded control state before any wipe execution exists', () => {
  const summary = summarizeWithdrawAllState({
    status: 'degraded',
    reason_code: 'state_load_failed',
    last_status: 'idle',
  });
  assert.equal(summary !== null, true);
  assert.equal(summary?.headline, 'Wipe degraded');
  assert.match(String(summary?.detail), /persisted wipe state could not be loaded/i);
});

test('summarizeWithdrawAllState surfaces available control state before any wipe execution exists', () => {
  const summary = summarizeWithdrawAllState({
    status: 'available',
    reason_code: 'ok',
    control_reason_code: 'ok',
    last_status: 'idle',
  });
  assert.equal(summary !== null, true);
  assert.equal(summary?.headline, 'Wipe ready');
  assert.match(String(summary?.detail), /ready for a fresh preview/i);
});


test('summarizeWithdrawAllState prefers current blocked control state over stale preview-ready state', () => {
  const summary = summarizeWithdrawAllState({
    status: 'blocked',
    reason_code: 'approved_destination_missing',
    last_status: 'preview_ready',
    last_reason_code: 'ok',
    preview_expired: false,
  });
  assert.equal(summary !== null, true);
  assert.equal(summary?.headline, 'Wipe blocked');
  assert.equal(summary?.status, 'blocked');
  assert.match(String(summary?.detail), /approved destination/i);
});

test('summarizeWithdrawAllState prefers current degraded control state over stale prepared wipe state', () => {
  const summary = summarizeWithdrawAllState({
    status: 'degraded',
    reason_code: 'state_load_failed',
    last_status: 'prepared',
    last_reason_code: 'ok',
    last_result: { status: 'prepared' },
  });
  assert.equal(summary !== null, true);
  assert.equal(summary?.headline, 'Wipe degraded');
  assert.equal(summary?.status, 'degraded');
  assert.match(String(summary?.detail), /persisted wipe state could not be loaded/i);
});

test('summarizeWithdrawAllState keeps submitted wipe execution visible even when current control is blocked', () => {
  const summary = summarizeWithdrawAllState({
    status: 'blocked',
    reason_code: 'command_center_paused',
    last_status: 'submitted',
    last_result: {
      status: 'submitted',
      submission_state: 'pending',
      submission_proof_reason: 'tx_visible',
      lifecycle_summary: {
        status: 'submitted',
        submission_state: 'pending',
        submission_proof_reason: 'tx_visible',
        outstanding_item_count: 1,
      },
    },
    last_result_summary: {
      status: 'submitted',
      submission_state: 'pending',
      submission_proof_reason: 'tx_visible',
      outstanding_item_count: 1,
    },
  });
  assert.equal(summary !== null, true);
  assert.equal(summary?.headline, 'Wipe pending');
  assert.equal(summary?.status, 'submitted');
  assert.match(String(summary?.detail), /awaiting confirmations/i);
});

test('summarizeWithdrawAllState surfaces preview-ready wipe state with deliberate execution guidance', () => {
  const summary = summarizeWithdrawAllState({
    last_status: 'preview_ready',
    last_reason_code: 'ok',
    preview_expired: false,
  });
  assert.equal(summary !== null, true);
  assert.equal(summary?.headline, 'Wipe preview ready');
  assert.match(String(summary?.detail), /deliberate execution confirmation/i);
});

test('summarizeWithdrawAllState surfaces expired wipe preview as a blocked retry condition', () => {
  const summary = summarizeWithdrawAllState({
    last_status: 'preview_ready',
    last_reason_code: 'ok',
    preview_expired: true,
  });
  assert.equal(summary !== null, true);
  assert.equal(summary?.headline, 'Wipe preview expired');
  assert.equal(summary?.ok, false);
  assert.equal(summary?.reasonCode, 'preview_expired');
  assert.match(String(summary?.detail), /generate a fresh preview/i);
});

test('summarizeWithdrawAllState surfaces preview-blocked reason instead of generic last-status text', () => {
  const summary = summarizeWithdrawAllState({
    last_status: 'preview_blocked',
    last_reason_code: 'capital_truth_degraded',
  });
  assert.equal(summary !== null, true);
  assert.equal(summary?.headline, 'Wipe preview blocked');
  assert.match(String(summary?.detail), /capital truth is degraded/i);
});

test('summarizeWithdrawAllState surfaces execute-blocked preview mismatch explicitly', () => {
  const summary = summarizeWithdrawAllState({
    last_status: 'execute_blocked',
    last_reason_code: 'preview_id_mismatch',
  });
  assert.equal(summary !== null, true);
  assert.equal(summary?.headline, 'Wipe blocked');
  assert.match(String(summary?.detail), /preview id no longer matched/i);
});

test('summarizeWithdrawAllState surfaces execute-blocked signer ownership mismatch explicitly', () => {
  const summary = summarizeWithdrawAllState({
    last_status: 'execute_blocked',
    last_reason_code: 'executor_owner_mismatch',
  });
  assert.equal(summary !== null, true);
  assert.equal(summary?.headline, 'Wipe blocked');
  assert.match(String(summary?.detail), /configured signer is not the executor owner/i);
});

test('summarizeWithdrawAllState surfaces preview-stale execution blocks with current backend reason', () => {
  const summary = summarizeWithdrawAllState({
    last_status: 'execute_blocked',
    last_reason_code: 'preview_stale',
    last_result: {
      reason_code: 'preview_stale',
      current_reason_code: 'capital_truth_degraded',
    },
  });
  assert.equal(summary !== null, true);
  assert.equal(summary?.headline, 'Wipe blocked');
  assert.equal(summary?.status, 'execute_blocked');
  assert.match(String(summary?.detail), /preview became stale/i);
  assert.match(String(summary?.detail), /capital truth degraded/i);
  assert.match(String(summary?.detail), /fresh preview/i);
});


test('shouldAutoRefreshWithdrawAllState stays active while wipe confirmations remain outstanding', () => {
  assert.equal(shouldAutoRefreshWithdrawAllState({
    last_status: 'submitted',
    last_result_summary: {
      outstanding_item_count: 2,
    },
  }), true);
  assert.equal(shouldAutoRefreshWithdrawAllState({
    last_status: 'completed',
    last_result_summary: {
      outstanding_item_count: 0,
    },
  }), false);
});

test('describeWithdrawAllRefresh reports active confirmation polling with last-check age', () => {
  const summary = describeWithdrawAllRefresh({
    last_status: 'submitted',
    last_result_summary: {
      outstanding_item_count: 1,
    },
  }, 1_000, 21_000);
  assert.match(summary, /Auto-refresh active/i);
  assert.match(summary, /last checked 20s ago/i);
});


test('nextWithdrawAllRefreshDelayMs follows backend cooldown eligibility when provided', () => {
  const delayMs = nextWithdrawAllRefreshDelayMs({
    last_status: 'submitted',
    last_result_summary: {
      outstanding_item_count: 1,
    },
    last_result_refresh: {
      next_eligible_refresh_ts_ms: 25_000,
      outstanding_item_count: 1,
    },
  }, 20_000);
  assert.equal(delayMs, 5_250);
});

test('describeWithdrawAllRefresh surfaces backend cooldown metadata when state is fresh', () => {
  const summary = describeWithdrawAllRefresh({
    last_status: 'submitted',
    last_result_summary: {
      outstanding_item_count: 1,
    },
    last_result_refresh: {
      status: 'skipped',
      reason_code: 'refresh_cooldown_active',
      checked_ts_ms: 21_000,
      next_eligible_refresh_ts_ms: 31_000,
      outstanding_item_count: 1,
    },
  }, 1_000, 25_000);
  assert.match(summary, /backend confirmation cooldown active/i);
  assert.match(summary, /next confirmation check eligible in 6s/i);
  assert.match(summary, /checked just now/i);
});

test('describeWithdrawAllRefresh surfaces backend revalidation progress after a refresh run', () => {
  const summary = describeWithdrawAllRefresh({
    last_status: 'submitted',
    last_result_summary: {
      outstanding_item_count: 2,
    },
    last_result_refresh: {
      status: 'refreshed',
      reason_code: 'refreshed_no_change',
      checked_ts_ms: 10_000,
      outstanding_item_count: 2,
    },
  }, 1_000, 16_000);
  assert.match(summary, /backend revalidated wipe confirmations/i);
  assert.match(summary, /2 items still awaiting confirmation/i);
  assert.match(summary, /last checked 6s ago/i);
});


test('describeWithdrawAllRefreshWarning surfaces persisted backend refresh degradation memory', () => {
  const summary = describeWithdrawAllRefreshWarning({
    last_status: 'submitted',
    last_result_summary: {
      outstanding_item_count: 1,
    },
    last_result_refresh_failure: {
      active: true,
      count: 3,
      reason_code: 'refresh_receipt_lookup_degraded',
      ts_ms: 12_000,
    },
  }, 18_000);
  assert.match(summary, /receipt lookup on the read RPC degraded/i);
  assert.match(summary, /3 consecutive backend refresh checks degraded/i);
  assert.match(summary, /last degraded 6s ago/i);
});

test('describeWithdrawAllRefresh surfaces missing read rpc distinctly from degraded receipt lookup', () => {
  const summary = describeWithdrawAllRefresh({
    last_status: 'submitted',
    last_result_summary: {
      outstanding_item_count: 1,
    },
    last_result_refresh: {
      status: 'skipped',
      reason_code: 'refresh_read_rpc_missing',
      checked_ts_ms: 12_000,
      outstanding_item_count: 1,
    },
  }, 10_000, 18_000);
  assert.match(summary, /no read RPC is configured/i);
});

test('describeWithdrawAllRefreshWarning stays empty when no persisted backend refresh degradation is active', () => {
  const summary = describeWithdrawAllRefreshWarning({
    last_status: 'submitted',
    last_result_summary: {
      outstanding_item_count: 1,
    },
    last_result_refresh_failure: {
      active: false,
      count: 0,
      reason_code: '',
      ts_ms: 0,
    },
  }, 18_000);
  assert.equal(summary, '');
});

test('describeWithdrawAllRefreshWarning surfaces repeated severity from backend failure metadata', () => {
  const summary = describeWithdrawAllRefreshWarning({
    last_status: 'submitted',
    last_result_summary: {
      outstanding_item_count: 1,
    },
    last_result_refresh_failure: {
      active: true,
      count: 2,
      reason_code: 'refresh_receipt_lookup_degraded',
      severity: 'repeated',
      ts_ms: 12_000,
    },
  }, 18_000);
  assert.match(summary, /repeatedly degraded/i);
  assert.match(summary, /receipt lookup on the read RPC degraded/i);
});


test('describeWithdrawAllRefreshWarning surfaces severe backend refresh degradation severity', () => {
  const summary = describeWithdrawAllRefreshWarning({
    last_status: 'submitted',
    last_result_summary: {
      outstanding_item_count: 1,
    },
    last_result_refresh_failure: {
      active: true,
      count: 4,
      reason_code: 'refresh_receipt_lookup_degraded',
      severity: 'severe',
      ts_ms: 12_000,
    },
  }, 18_000);
  assert.match(summary, /severely degraded/i);
  assert.match(summary, /4 consecutive backend refresh checks degraded/i);
});


test('describeWithdrawAllRefreshWarning surfaces backend decay timing for stale degraded refresh memory', () => {
  const summary = describeWithdrawAllRefreshWarning({
    last_status: 'submitted',
    last_result_summary: {
      outstanding_item_count: 1,
    },
    last_result_refresh_failure: {
      active: true,
      count: 2,
      reason_code: 'refresh_receipt_lookup_degraded',
      ts_ms: 12_000,
      next_decay_ts_ms: 42_000,
    },
  }, 18_000);
  assert.match(summary, /2 consecutive backend refresh checks degraded/i);
  assert.match(summary, /next stale degradation decay in 24s/i);
});

test('describeWithdrawAllRefreshWarning surfaces decay eligibility once stale degraded refresh memory can age out', () => {
  const summary = describeWithdrawAllRefreshWarning({
    last_status: 'submitted',
    last_result_summary: {
      outstanding_item_count: 1,
    },
    last_result_refresh_failure: {
      active: true,
      count: 1,
      reason_code: 'refresh_receipt_lookup_degraded',
      ts_ms: 12_000,
      next_decay_ts_ms: 17_000,
    },
  }, 18_000);
  assert.match(summary, /stale degradation is eligible to decay now/i);
});
