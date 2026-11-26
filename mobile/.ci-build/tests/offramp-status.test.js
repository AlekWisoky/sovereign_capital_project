"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const node_assert_1 = require("node:assert");
const offRampStatus_1 = require("../src/utils/offRampStatus");
(0, node_test_1.default)('summarizeWithdrawExecution reports pending submission without claiming completion', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawExecution)({ ok: true, status: 'pending', tx_hash: '0x' + '1'.repeat(64) }, 'Withdraw');
    node_assert_1.strict.equal(summary.headline, 'Withdraw pending');
    node_assert_1.strict.match(summary.detail, /pending confirmation/i);
});
(0, node_test_1.default)('summarizeWithdrawExecution reports read-rpc visibility proof for pending txs', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawExecution)({ ok: true, status: 'pending', tx_proof_reason: 'tx_visible', tx_hash: '0x' + '4'.repeat(64) }, 'Withdraw');
    node_assert_1.strict.equal(summary.headline, 'Withdraw pending');
    node_assert_1.strict.match(summary.detail, /visible on the read RPC/i);
});
(0, node_test_1.default)('summarizeWithdrawExecution distinguishes degraded receipt lookup from generic receipt unavailability', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawExecution)({ ok: true, status: 'receipt_unavailable', tx_proof_reason: 'receipt_lookup_degraded', tx_hash: '0x' + '5'.repeat(64) }, 'Convert+withdraw');
    node_assert_1.strict.equal(summary.headline, 'Convert+withdraw receipt unavailable');
    node_assert_1.strict.match(summary.detail, /receipt lookup on the read RPC degraded/i);
});
(0, node_test_1.default)('summarizeWithdrawExecution distinguishes private submission from generic sent status', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawExecution)({ ok: true, status: 'sent', tx_proof_reason: 'private_no_public_receipt', tx_hash: '0x' + '6'.repeat(64) }, 'Withdraw');
    node_assert_1.strict.equal(summary.headline, 'Withdraw sent');
    node_assert_1.strict.match(summary.detail, /private submission/i);
});
(0, node_test_1.default)('summarizeWithdrawExecution reports on-chain revert as failure', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawExecution)({ ok: false, reason_code: 'receipt_reverted', tx_hash: '0x' + '2'.repeat(64) }, 'Convert+withdraw');
    node_assert_1.strict.equal(summary.ok, false);
    node_assert_1.strict.equal(summary.status, 'receipt_reverted');
    node_assert_1.strict.match(summary.detail, /reverted on-chain/i);
});
(0, node_test_1.default)('summarizeWithdrawAllExecution distinguishes submitted from completed', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawAllExecution)({ ok: true, result: { status: 'submitted', submission_state: 'sent' } });
    node_assert_1.strict.equal(summary.headline, 'Wipe sent');
    node_assert_1.strict.match(summary.detail, /not visible yet/i);
});
(0, node_test_1.default)('summarizeWithdrawAllExecution uses read-rpc visibility proof for pending wipe submissions', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawAllExecution)({ ok: true, result: { status: 'submitted', submission_state: 'pending', submission_proof_reason: 'tx_visible' } });
    node_assert_1.strict.equal(summary.headline, 'Wipe pending');
    node_assert_1.strict.match(summary.detail, /visible on the read RPC/i);
});
(0, node_test_1.default)('summarizeWithdrawAllExecution distinguishes private submission from generic sent wipe status', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawAllExecution)({ ok: true, result: { status: 'submitted', submission_state: 'sent', submission_proof_reason: 'private_no_public_receipt' } });
    node_assert_1.strict.equal(summary.headline, 'Wipe sent');
    node_assert_1.strict.match(summary.detail, /private submission/i);
});
(0, node_test_1.default)('summarizeWithdrawAllState surfaces failed last execution from persisted state', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawAllState)({
        last_status: 'execute_failed',
        last_reason_code: 'receipt_reverted',
        last_result: { failed_item: { tx_hash: '0x' + '3'.repeat(64) } },
    });
    node_assert_1.strict.equal(summary !== null, true);
    node_assert_1.strict.equal(summary?.headline, 'Wipe failed');
    node_assert_1.strict.match(String(summary?.detail), /reverted on-chain/i);
});
(0, node_test_1.default)('summarizeWithdrawAllState includes item-level lifecycle counts from persisted state', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawAllState)({
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
    node_assert_1.strict.equal(summary !== null, true);
    node_assert_1.strict.equal(summary?.headline, 'Wipe submitted');
    node_assert_1.strict.match(String(summary?.detail), /1 item confirmed/i);
    node_assert_1.strict.match(String(summary?.detail), /2 items awaiting confirmation/i);
});
(0, node_test_1.default)('summarizeWithdrawAllState surfaces blocked control state before any wipe execution exists', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawAllState)({
        status: 'blocked',
        reason_code: 'approved_destination_missing',
        control_reason_code: 'approved_destination_missing',
        last_status: 'idle',
    });
    node_assert_1.strict.equal(summary !== null, true);
    node_assert_1.strict.equal(summary?.headline, 'Wipe blocked');
    node_assert_1.strict.match(String(summary?.detail), /blocked until an approved destination is configured/i);
});
(0, node_test_1.default)('summarizeWithdrawAllState surfaces degraded control state before any wipe execution exists', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawAllState)({
        status: 'degraded',
        reason_code: 'state_load_failed',
        last_status: 'idle',
    });
    node_assert_1.strict.equal(summary !== null, true);
    node_assert_1.strict.equal(summary?.headline, 'Wipe degraded');
    node_assert_1.strict.match(String(summary?.detail), /persisted wipe state could not be loaded/i);
});
(0, node_test_1.default)('summarizeWithdrawAllState surfaces available control state before any wipe execution exists', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawAllState)({
        status: 'available',
        reason_code: 'ok',
        control_reason_code: 'ok',
        last_status: 'idle',
    });
    node_assert_1.strict.equal(summary !== null, true);
    node_assert_1.strict.equal(summary?.headline, 'Wipe ready');
    node_assert_1.strict.match(String(summary?.detail), /ready for a fresh preview/i);
});
(0, node_test_1.default)('summarizeWithdrawAllState prefers current blocked control state over stale preview-ready state', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawAllState)({
        status: 'blocked',
        reason_code: 'approved_destination_missing',
        last_status: 'preview_ready',
        last_reason_code: 'ok',
        preview_expired: false,
    });
    node_assert_1.strict.equal(summary !== null, true);
    node_assert_1.strict.equal(summary?.headline, 'Wipe blocked');
    node_assert_1.strict.equal(summary?.status, 'blocked');
    node_assert_1.strict.match(String(summary?.detail), /approved destination/i);
});
(0, node_test_1.default)('summarizeWithdrawAllState prefers current degraded control state over stale prepared wipe state', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawAllState)({
        status: 'degraded',
        reason_code: 'state_load_failed',
        last_status: 'prepared',
        last_reason_code: 'ok',
        last_result: { status: 'prepared' },
    });
    node_assert_1.strict.equal(summary !== null, true);
    node_assert_1.strict.equal(summary?.headline, 'Wipe degraded');
    node_assert_1.strict.equal(summary?.status, 'degraded');
    node_assert_1.strict.match(String(summary?.detail), /persisted wipe state could not be loaded/i);
});
(0, node_test_1.default)('summarizeWithdrawAllState keeps submitted wipe execution visible even when current control is blocked', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawAllState)({
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
    node_assert_1.strict.equal(summary !== null, true);
    node_assert_1.strict.equal(summary?.headline, 'Wipe pending');
    node_assert_1.strict.equal(summary?.status, 'submitted');
    node_assert_1.strict.match(String(summary?.detail), /awaiting confirmations/i);
});
(0, node_test_1.default)('summarizeWithdrawAllState surfaces preview-ready wipe state with deliberate execution guidance', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawAllState)({
        last_status: 'preview_ready',
        last_reason_code: 'ok',
        preview_expired: false,
    });
    node_assert_1.strict.equal(summary !== null, true);
    node_assert_1.strict.equal(summary?.headline, 'Wipe preview ready');
    node_assert_1.strict.match(String(summary?.detail), /deliberate execution confirmation/i);
});
(0, node_test_1.default)('summarizeWithdrawAllState surfaces expired wipe preview as a blocked retry condition', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawAllState)({
        last_status: 'preview_ready',
        last_reason_code: 'ok',
        preview_expired: true,
    });
    node_assert_1.strict.equal(summary !== null, true);
    node_assert_1.strict.equal(summary?.headline, 'Wipe preview expired');
    node_assert_1.strict.equal(summary?.ok, false);
    node_assert_1.strict.equal(summary?.reasonCode, 'preview_expired');
    node_assert_1.strict.match(String(summary?.detail), /generate a fresh preview/i);
});
(0, node_test_1.default)('summarizeWithdrawAllState surfaces preview-blocked reason instead of generic last-status text', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawAllState)({
        last_status: 'preview_blocked',
        last_reason_code: 'capital_truth_degraded',
    });
    node_assert_1.strict.equal(summary !== null, true);
    node_assert_1.strict.equal(summary?.headline, 'Wipe preview blocked');
    node_assert_1.strict.match(String(summary?.detail), /capital truth is degraded/i);
});
(0, node_test_1.default)('summarizeWithdrawAllState surfaces execute-blocked preview mismatch explicitly', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawAllState)({
        last_status: 'execute_blocked',
        last_reason_code: 'preview_id_mismatch',
    });
    node_assert_1.strict.equal(summary !== null, true);
    node_assert_1.strict.equal(summary?.headline, 'Wipe blocked');
    node_assert_1.strict.match(String(summary?.detail), /preview id no longer matched/i);
});
(0, node_test_1.default)('summarizeWithdrawAllState surfaces execute-blocked signer ownership mismatch explicitly', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawAllState)({
        last_status: 'execute_blocked',
        last_reason_code: 'executor_owner_mismatch',
    });
    node_assert_1.strict.equal(summary !== null, true);
    node_assert_1.strict.equal(summary?.headline, 'Wipe blocked');
    node_assert_1.strict.match(String(summary?.detail), /configured signer is not the executor owner/i);
});
(0, node_test_1.default)('summarizeWithdrawAllState surfaces preview-stale execution blocks with current backend reason', () => {
    const summary = (0, offRampStatus_1.summarizeWithdrawAllState)({
        last_status: 'execute_blocked',
        last_reason_code: 'preview_stale',
        last_result: {
            reason_code: 'preview_stale',
            current_reason_code: 'capital_truth_degraded',
        },
    });
    node_assert_1.strict.equal(summary !== null, true);
    node_assert_1.strict.equal(summary?.headline, 'Wipe blocked');
    node_assert_1.strict.equal(summary?.status, 'execute_blocked');
    node_assert_1.strict.match(String(summary?.detail), /preview became stale/i);
    node_assert_1.strict.match(String(summary?.detail), /capital truth degraded/i);
    node_assert_1.strict.match(String(summary?.detail), /fresh preview/i);
});
(0, node_test_1.default)('shouldAutoRefreshWithdrawAllState stays active while wipe confirmations remain outstanding', () => {
    node_assert_1.strict.equal((0, offRampStatus_1.shouldAutoRefreshWithdrawAllState)({
        last_status: 'submitted',
        last_result_summary: {
            outstanding_item_count: 2,
        },
    }), true);
    node_assert_1.strict.equal((0, offRampStatus_1.shouldAutoRefreshWithdrawAllState)({
        last_status: 'completed',
        last_result_summary: {
            outstanding_item_count: 0,
        },
    }), false);
});
(0, node_test_1.default)('describeWithdrawAllRefresh reports active confirmation polling with last-check age', () => {
    const summary = (0, offRampStatus_1.describeWithdrawAllRefresh)({
        last_status: 'submitted',
        last_result_summary: {
            outstanding_item_count: 1,
        },
    }, 1000, 21000);
    node_assert_1.strict.match(summary, /Auto-refresh active/i);
    node_assert_1.strict.match(summary, /last checked 20s ago/i);
});
(0, node_test_1.default)('nextWithdrawAllRefreshDelayMs follows backend cooldown eligibility when provided', () => {
    const delayMs = (0, offRampStatus_1.nextWithdrawAllRefreshDelayMs)({
        last_status: 'submitted',
        last_result_summary: {
            outstanding_item_count: 1,
        },
        last_result_refresh: {
            next_eligible_refresh_ts_ms: 25000,
            outstanding_item_count: 1,
        },
    }, 20000);
    node_assert_1.strict.equal(delayMs, 5250);
});
(0, node_test_1.default)('describeWithdrawAllRefresh surfaces backend cooldown metadata when state is fresh', () => {
    const summary = (0, offRampStatus_1.describeWithdrawAllRefresh)({
        last_status: 'submitted',
        last_result_summary: {
            outstanding_item_count: 1,
        },
        last_result_refresh: {
            status: 'skipped',
            reason_code: 'refresh_cooldown_active',
            checked_ts_ms: 21000,
            next_eligible_refresh_ts_ms: 31000,
            outstanding_item_count: 1,
        },
    }, 1000, 25000);
    node_assert_1.strict.match(summary, /backend confirmation cooldown active/i);
    node_assert_1.strict.match(summary, /next confirmation check eligible in 6s/i);
    node_assert_1.strict.match(summary, /checked just now/i);
});
(0, node_test_1.default)('describeWithdrawAllRefresh surfaces backend revalidation progress after a refresh run', () => {
    const summary = (0, offRampStatus_1.describeWithdrawAllRefresh)({
        last_status: 'submitted',
        last_result_summary: {
            outstanding_item_count: 2,
        },
        last_result_refresh: {
            status: 'refreshed',
            reason_code: 'refreshed_no_change',
            checked_ts_ms: 10000,
            outstanding_item_count: 2,
        },
    }, 1000, 16000);
    node_assert_1.strict.match(summary, /backend revalidated wipe confirmations/i);
    node_assert_1.strict.match(summary, /2 items still awaiting confirmation/i);
    node_assert_1.strict.match(summary, /last checked 6s ago/i);
});
(0, node_test_1.default)('describeWithdrawAllRefreshWarning surfaces persisted backend refresh degradation memory', () => {
    const summary = (0, offRampStatus_1.describeWithdrawAllRefreshWarning)({
        last_status: 'submitted',
        last_result_summary: {
            outstanding_item_count: 1,
        },
        last_result_refresh_failure: {
            active: true,
            count: 3,
            reason_code: 'refresh_receipt_lookup_degraded',
            ts_ms: 12000,
        },
    }, 18000);
    node_assert_1.strict.match(summary, /receipt lookup on the read RPC degraded/i);
    node_assert_1.strict.match(summary, /3 consecutive backend refresh checks degraded/i);
    node_assert_1.strict.match(summary, /last degraded 6s ago/i);
});
(0, node_test_1.default)('describeWithdrawAllRefresh surfaces missing read rpc distinctly from degraded receipt lookup', () => {
    const summary = (0, offRampStatus_1.describeWithdrawAllRefresh)({
        last_status: 'submitted',
        last_result_summary: {
            outstanding_item_count: 1,
        },
        last_result_refresh: {
            status: 'skipped',
            reason_code: 'refresh_read_rpc_missing',
            checked_ts_ms: 12000,
            outstanding_item_count: 1,
        },
    }, 10000, 18000);
    node_assert_1.strict.match(summary, /no read RPC is configured/i);
});
(0, node_test_1.default)('describeWithdrawAllRefreshWarning stays empty when no persisted backend refresh degradation is active', () => {
    const summary = (0, offRampStatus_1.describeWithdrawAllRefreshWarning)({
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
    }, 18000);
    node_assert_1.strict.equal(summary, '');
});
(0, node_test_1.default)('describeWithdrawAllRefreshWarning surfaces repeated severity from backend failure metadata', () => {
    const summary = (0, offRampStatus_1.describeWithdrawAllRefreshWarning)({
        last_status: 'submitted',
        last_result_summary: {
            outstanding_item_count: 1,
        },
        last_result_refresh_failure: {
            active: true,
            count: 2,
            reason_code: 'refresh_receipt_lookup_degraded',
            severity: 'repeated',
            ts_ms: 12000,
        },
    }, 18000);
    node_assert_1.strict.match(summary, /repeatedly degraded/i);
    node_assert_1.strict.match(summary, /receipt lookup on the read RPC degraded/i);
});
(0, node_test_1.default)('describeWithdrawAllRefreshWarning surfaces severe backend refresh degradation severity', () => {
    const summary = (0, offRampStatus_1.describeWithdrawAllRefreshWarning)({
        last_status: 'submitted',
        last_result_summary: {
            outstanding_item_count: 1,
        },
        last_result_refresh_failure: {
            active: true,
            count: 4,
            reason_code: 'refresh_receipt_lookup_degraded',
            severity: 'severe',
            ts_ms: 12000,
        },
    }, 18000);
    node_assert_1.strict.match(summary, /severely degraded/i);
    node_assert_1.strict.match(summary, /4 consecutive backend refresh checks degraded/i);
});
(0, node_test_1.default)('describeWithdrawAllRefreshWarning surfaces backend decay timing for stale degraded refresh memory', () => {
    const summary = (0, offRampStatus_1.describeWithdrawAllRefreshWarning)({
        last_status: 'submitted',
        last_result_summary: {
            outstanding_item_count: 1,
        },
        last_result_refresh_failure: {
            active: true,
            count: 2,
            reason_code: 'refresh_receipt_lookup_degraded',
            ts_ms: 12000,
            next_decay_ts_ms: 42000,
        },
    }, 18000);
    node_assert_1.strict.match(summary, /2 consecutive backend refresh checks degraded/i);
    node_assert_1.strict.match(summary, /next stale degradation decay in 24s/i);
});
(0, node_test_1.default)('describeWithdrawAllRefreshWarning surfaces decay eligibility once stale degraded refresh memory can age out', () => {
    const summary = (0, offRampStatus_1.describeWithdrawAllRefreshWarning)({
        last_status: 'submitted',
        last_result_summary: {
            outstanding_item_count: 1,
        },
        last_result_refresh_failure: {
            active: true,
            count: 1,
            reason_code: 'refresh_receipt_lookup_degraded',
            ts_ms: 12000,
            next_decay_ts_ms: 17000,
        },
    }, 18000);
    node_assert_1.strict.match(summary, /stale degradation is eligible to decay now/i);
});
