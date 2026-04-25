export type OffRampExecutionSummary = {
  headline: string;
  detail: string;
  ok: boolean;
  status: string;
  reasonCode: string;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : null;
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : (value === undefined || value === null ? '' : String(value));
}

function humanizeReason(value: string): string {
  const raw = text(value).trim();
  if (!raw) return 'unknown reason';
  return raw.replace(/_/g, ' ');
}

function shortHash(value: string): string {
  const tx = text(value).trim();
  return /^0x[0-9a-fA-F]{64}$/.test(tx) ? `${tx.slice(0, 10)}…${tx.slice(-8)}` : tx;
}

function txSuffix(record: Record<string, unknown> | null): string {
  const txHash = text(record?.tx_hash ?? record?.txHash ?? '');
  return txHash ? ` · ${shortHash(txHash)}` : '';
}

function num(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? Math.trunc(parsed) : 0;
}

function pluralize(count: number, singular: string, plural: string = `${singular}s`): string {
  return count === 1 ? singular : plural;
}

function lifecycleDetail(lifecycle: Record<string, unknown> | null): string {
  if (!lifecycle) return '';
  const confirmed = num(lifecycle.confirmed_item_count);
  const outstanding = num(lifecycle.outstanding_item_count);
  const reverted = num(lifecycle.reverted_item_count);
  const failed = num(lifecycle.failed_item_count);
  const attempted = num(lifecycle.attempted_item_count ?? lifecycle.item_count);
  const parts: string[] = [];
  if (confirmed > 0) parts.push(`${confirmed} ${pluralize(confirmed, 'item')} confirmed`);
  if (outstanding > 0) parts.push(`${outstanding} ${pluralize(outstanding, 'item')} awaiting confirmation`);
  if (reverted > 0) parts.push(`${reverted} ${pluralize(reverted, 'item')} reverted`);
  if (failed > reverted) parts.push(`${failed - reverted} ${pluralize(failed - reverted, 'item')} failed`);
  if (!parts.length && attempted > 0) parts.push(`${attempted} ${pluralize(attempted, 'item')} tracked`);
  return parts.join(', ');
}

function refreshAgeDetail(lastRefreshAtMs: number, nowMs: number): string {
  if (!(lastRefreshAtMs > 0)) return 'waiting for next confirmation check';
  const ageMs = Math.max(0, nowMs - lastRefreshAtMs);
  const ageSeconds = Math.floor(ageMs / 1000);
  if (ageSeconds < 5) return 'checked just now';
  if (ageSeconds < 60) return `last checked ${ageSeconds}s ago`;
  const ageMinutes = Math.floor(ageSeconds / 60);
  return `last checked ${ageMinutes}m ago`;
}

function refreshFailureAgeDetail(lastFailureAtMs: number, nowMs: number): string {
  if (!(lastFailureAtMs > 0)) return 'degradation timing unavailable';
  const ageMs = Math.max(0, nowMs - lastFailureAtMs);
  const ageSeconds = Math.floor(ageMs / 1000);
  if (ageSeconds < 5) return 'last degraded just now';
  if (ageSeconds < 60) return `last degraded ${ageSeconds}s ago`;
  const ageMinutes = Math.floor(ageSeconds / 60);
  return `last degraded ${ageMinutes}m ago`;
}

function refreshMetadata(state: unknown): Record<string, unknown> | null {
  return asRecord(asRecord(state)?.last_result_refresh);
}

function refreshFailureMetadata(state: unknown): Record<string, unknown> | null {
  const record = asRecord(state);
  const nested = asRecord(record?.last_result_refresh_failure);
  if (nested) return nested;
  const refresh = refreshMetadata(state);
  if (!refresh) return null;
  return {
    active: refresh.failure_active,
    count: refresh.failure_count,
    reason_code: refresh.failure_reason_code,
    ts_ms: refresh.failure_ts_ms,
    next_decay_ts_ms: refresh.failure_next_decay_ts_ms,
    decay_interval_ms: refresh.failure_decay_interval_ms,
  };
}

function refreshTimestampMs(state: unknown, fallbackTsMs: number): number {
  return num(refreshMetadata(state)?.checked_ts_ms) || Math.max(0, Math.trunc(fallbackTsMs || 0));
}

function refreshFailureTimestampMs(state: unknown): number {
  return num(refreshFailureMetadata(state)?.ts_ms);
}

function refreshFailureNextDecayTimestampMs(state: unknown): number {
  return num(refreshFailureMetadata(state)?.next_decay_ts_ms);
}

function refreshFailureSeverity(state: unknown): string {
  const failure = refreshFailureMetadata(state);
  const severity = text(failure?.severity ?? refreshMetadata(state)?.failure_severity ?? '');
  return severity || 'none';
}

function nextEligibleDelayDetail(nextEligibleTsMs: number, nowMs: number): string {
  if (!(nextEligibleTsMs > nowMs)) return 'next confirmation check eligible now';
  const remainingSeconds = Math.max(1, Math.ceil((nextEligibleTsMs - nowMs) / 1000));
  return `next confirmation check eligible in ${remainingSeconds}s`;
}

function nextFailureDecayDetail(nextDecayTsMs: number, nowMs: number): string {
  if (!(nextDecayTsMs > 0)) return '';
  if (nextDecayTsMs <= nowMs) return 'stale degradation is eligible to decay now';
  const remainingSeconds = Math.max(1, Math.ceil((nextDecayTsMs - nowMs) / 1000));
  return `next stale degradation decay in ${remainingSeconds}s`;
}

export function shouldAutoRefreshWithdrawAllState(state: unknown): boolean {
  const record = asRecord(state);
  if (!record) return false;
  const lastStatus = text(record.last_status ?? record.status ?? '');
  if (lastStatus === 'submitted') return true;
  const lifecycle = asRecord(record.last_result_summary ?? asRecord(record.last_result)?.lifecycle_summary);
  return num(lifecycle?.outstanding_item_count) > 0;
}

export function nextWithdrawAllRefreshDelayMs(state: unknown, nowMs: number = Date.now()): number {
  if (!shouldAutoRefreshWithdrawAllState(state)) return 0;
  const refresh = refreshMetadata(state);
  const nextEligibleTsMs = num(refresh?.next_eligible_refresh_ts_ms);
  if (nextEligibleTsMs > nowMs) {
    return Math.max(1000, nextEligibleTsMs - nowMs + 250);
  }
  return 15000;
}

export function describeWithdrawAllRefresh(state: unknown, lastRefreshAtMs: number, nowMs: number = Date.now()): string {
  if (!shouldAutoRefreshWithdrawAllState(state)) return '';
  const refresh = refreshMetadata(state);
  const refreshStatus = text(refresh?.status ?? '');
  const refreshReason = text(refresh?.reason_code ?? '');
  const checkedTsMs = refreshTimestampMs(state, lastRefreshAtMs);
  const ageDetail = refreshAgeDetail(checkedTsMs, nowMs);
  const outstanding = num(refresh?.outstanding_item_count);
  const outstandingDetail = outstanding > 0 ? ` · ${outstanding} ${pluralize(outstanding, 'item')} still awaiting confirmation` : '';
  const nextEligibleTsMs = num(refresh?.next_eligible_refresh_ts_ms);

  if (refreshReason === 'refresh_cooldown_active') {
    return `Auto-refresh active · backend confirmation cooldown active · ${nextEligibleDelayDetail(nextEligibleTsMs, nowMs)} · ${ageDetail}.`;
  }
  if (refreshReason === 'refresh_read_rpc_missing' || refreshReason === 'read_rpc_unavailable') {
    return `Auto-refresh active · backend could not revalidate wipe confirmations because no read RPC is configured · ${ageDetail}.`;
  }
  if (refreshReason === 'refresh_receipt_lookup_degraded') {
    return `Auto-refresh active · backend could not revalidate wipe confirmations because receipt lookup on the read RPC degraded · ${ageDetail}.`;
  }
  if (refreshStatus === 'refreshed' && refreshReason === 'refreshed_updated') {
    return `Auto-refresh active · backend revalidated wipe confirmations and strengthened the persisted wipe state · ${ageDetail}${outstandingDetail}.`;
  }
  if (refreshStatus === 'refreshed' && refreshReason === 'refreshed_no_change') {
    return `Auto-refresh active · backend revalidated wipe confirmations and no stronger proof was available yet · ${ageDetail}${outstandingDetail}.`;
  }
  return `Auto-refresh active while wipe confirmations remain outstanding · ${ageDetail}.`;
}

export function describeWithdrawAllRefreshWarning(state: unknown, nowMs: number = Date.now()): string {
  if (!shouldAutoRefreshWithdrawAllState(state)) return '';
  const failure = refreshFailureMetadata(state);
  const failureCount = num(failure?.count);
  const failureReason = text(failure?.reason_code ?? '');
  const active = Boolean(failure?.active === true || (failureCount > 0 && failureReason));
  if (!active) return '';
  const failureSeverity = refreshFailureSeverity(state);
  const failureAge = refreshFailureAgeDetail(refreshFailureTimestampMs(state), nowMs);
  const consecutiveDetail = failureCount > 1 ? ` · ${failureCount} consecutive backend refresh checks degraded` : '';
  const nextDecayDetail = nextFailureDecayDetail(refreshFailureNextDecayTimestampMs(state), nowMs);
  const decaySuffix = nextDecayDetail ? ` · ${nextDecayDetail}` : '';
  const prefix = failureSeverity === 'severe'
    ? 'Backend refresh is severely degraded'
    : (failureSeverity === 'repeated' ? 'Backend refresh is repeatedly degraded' : 'Backend refresh degraded');
  if (failureReason === 'refresh_read_rpc_missing' || failureReason === 'read_rpc_unavailable') {
    return `${prefix} because no read RPC is configured${consecutiveDetail} · ${failureAge}${decaySuffix}.`;
  }
  if (failureReason === 'refresh_receipt_lookup_degraded') {
    return `${prefix} because receipt lookup on the read RPC degraded${consecutiveDetail} · ${failureAge}${decaySuffix}.`;
  }
  return `${prefix} (${humanizeReason(failureReason)})${consecutiveDetail} · ${failureAge}${decaySuffix}.`;
}

export function summarizeWithdrawExecution(payload: unknown, actionLabel: string = 'Withdraw'): OffRampExecutionSummary {
  const record = asRecord(payload);
  const ok = record?.ok === true;
  const reasonCode = text(record?.reason_code ?? record?.reason ?? record?.error ?? '');
  const txStatus = text(record?.tx_status ?? record?.status ?? '');
  const txProofReason = text(record?.tx_proof_reason ?? record?.proof_reason ?? '');
  const suffix = txSuffix(record);

  if (!ok) {
    if (reasonCode === 'receipt_reverted') {
      return {
        headline: `${actionLabel} reverted`,
        detail: `${actionLabel} was submitted but reverted on-chain${suffix}.`,
        ok: false,
        status: 'receipt_reverted',
        reasonCode,
      };
    }
    const reason = humanizeReason(reasonCode);
    return {
      headline: `${actionLabel} blocked`,
      detail: `${actionLabel} did not proceed · ${reason}.`,
      ok: false,
      status: txStatus || 'blocked',
      reasonCode,
    };
  }

  switch (txStatus) {
    case 'mined_success':
      return {
        headline: `${actionLabel} confirmed`,
        detail: `${actionLabel} mined successfully${suffix}.`,
        ok: true,
        status: txStatus,
        reasonCode,
      };
    case 'pending': {
      const detail = txProofReason === 'tx_visible'
        ? `${actionLabel} is visible on the read RPC and awaiting confirmation${suffix}.`
        : `${actionLabel} was submitted and is pending confirmation${suffix}.`;
      return {
        headline: `${actionLabel} pending`,
        detail,
        ok: true,
        status: txStatus,
        reasonCode,
      };
    }
    case 'sent': {
      let detail = `${actionLabel} was accepted for submission but does not have a public receipt yet${suffix}.`;
      if (txProofReason === 'private_no_public_receipt') {
        detail = `${actionLabel} was accepted for private submission and does not have a public receipt yet${suffix}.`;
      } else if (txProofReason === 'receipt_lookup_degraded') {
        detail = `${actionLabel} was accepted for submission but receipt lookup on the read RPC degraded${suffix}.`;
      }
      return {
        headline: `${actionLabel} sent`,
        detail,
        ok: true,
        status: txStatus,
        reasonCode,
      };
    }
    case 'receipt_unavailable': {
      let detail = `${actionLabel} was submitted but receipt visibility is not available yet${suffix}.`;
      if (txProofReason === 'receipt_lookup_degraded') {
        detail = `${actionLabel} was submitted but receipt lookup on the read RPC degraded${suffix}.`;
      } else if (txProofReason === 'tx_not_visible') {
        detail = `${actionLabel} was submitted but the read RPC cannot yet prove receipt or transaction visibility${suffix}.`;
      } else if (txProofReason === 'receipt_observed') {
        detail = `${actionLabel} was submitted and a receipt was observed, but final receipt status is not available yet${suffix}.`;
      }
      return {
        headline: `${actionLabel} receipt unavailable`,
        detail,
        ok: true,
        status: txStatus,
        reasonCode,
      };
    }
    default:
      return {
        headline: `${actionLabel} submitted`,
        detail: `${actionLabel} returned status ${txStatus || 'submitted'}${suffix}.`,
        ok: true,
        status: txStatus || 'submitted',
        reasonCode,
      };
  }
}

export function summarizeWithdrawAllExecution(payload: unknown): OffRampExecutionSummary {
  const record = asRecord(payload);
  const ok = record?.ok === true;
  const reasonCode = text(record?.reason_code ?? record?.reason ?? record?.error ?? '');
  const result = asRecord(record?.result);
  const lifecycle = asRecord(result?.lifecycle_summary ?? record?.last_result_summary ?? record?.lifecycle_summary);
  const status = text(result?.status ?? lifecycle?.status ?? record?.status ?? '');
  const submissionState = text(result?.submission_state ?? lifecycle?.submission_state ?? record?.submission_state ?? '');
  const submissionProofReason = text(result?.submission_proof_reason ?? lifecycle?.submission_proof_reason ?? record?.submission_proof_reason ?? '');
  const failedItem = asRecord(result?.failed_item);
  const lifecycleText = lifecycleDetail(lifecycle);

  if (!ok) {
    if (reasonCode === 'receipt_reverted') {
      return {
        headline: 'Wipe failed',
        detail: `A submitted withdrawal reverted on-chain${txSuffix(failedItem)}${lifecycleText ? ` · ${lifecycleText}` : ''}.`,
        ok: false,
        status: 'receipt_reverted',
        reasonCode,
      };
    }
    return {
      headline: 'Wipe blocked',
      detail: `Withdraw-everything did not proceed · ${humanizeReason(reasonCode)}${lifecycleText ? ` · ${lifecycleText}` : ''}.`,
      ok: false,
      status: status || 'blocked',
      reasonCode,
    };
  }

  if (status === 'completed' || submissionState === 'mined_success') {
    const attempted = num(lifecycle?.attempted_item_count ?? lifecycle?.item_count);
    return {
      headline: 'Wipe completed',
      detail: attempted > 0 ? `All ${attempted} submitted ${pluralize(attempted, 'withdrawal')} mined successfully.` : 'All submitted withdrawals mined successfully.',
      ok: true,
      status: 'completed',
      reasonCode,
    };
  }

  if (status === 'submitted') {
    const suffix = lifecycleText ? ` · ${lifecycleText}.` : '.';
    switch (submissionState) {
      case 'pending': {
        const detail = submissionProofReason === 'tx_visible'
          ? `Withdraw-everything is visible on the read RPC and awaiting confirmations${suffix}`
          : `Withdraw-everything was submitted and is awaiting confirmations${suffix}`;
        return {
          headline: 'Wipe pending',
          detail,
          ok: true,
          status,
          reasonCode,
        };
      }
      case 'sent': {
        let detail = `Withdraw-everything was accepted for submission but public receipts are not visible yet${suffix}`;
        if (submissionProofReason === 'private_no_public_receipt') {
          detail = `Withdraw-everything was accepted for private submission and does not have a public receipt yet${suffix}`;
        } else if (submissionProofReason === 'receipt_lookup_degraded') {
          detail = `Withdraw-everything was accepted for submission but receipt lookup on the read RPC degraded${suffix}`;
        }
        return {
          headline: 'Wipe sent',
          detail,
          ok: true,
          status,
          reasonCode,
        };
      }
      case 'receipt_unavailable': {
        let detail = `Withdraw-everything was submitted but receipt visibility is not available yet${suffix}`;
        if (submissionProofReason === 'receipt_lookup_degraded') {
          detail = `Withdraw-everything was submitted but receipt lookup on the read RPC degraded${suffix}`;
        } else if (submissionProofReason === 'tx_not_visible') {
          detail = `Withdraw-everything was submitted but the read RPC cannot yet prove receipt or transaction visibility${suffix}`;
        } else if (submissionProofReason === 'receipt_observed') {
          detail = `Withdraw-everything was submitted and a receipt was observed, but final receipt status is not available yet${suffix}`;
        }
        return {
          headline: 'Wipe receipt unavailable',
          detail,
          ok: true,
          status,
          reasonCode,
        };
      }
      case 'mixed':
        return {
          headline: 'Wipe submitted',
          detail: `Withdraw-everything was submitted with mixed item-level execution states${suffix}`,
          ok: true,
          status,
          reasonCode,
        };
      default:
        return {
          headline: 'Wipe submitted',
          detail: `Withdraw-everything was submitted and is not yet fully confirmed${suffix}`,
          ok: true,
          status,
          reasonCode,
        };
    }
  }

  if (status === 'prepared') {
    return {
      headline: 'Wipe prepared',
      detail: `Withdraw-everything generated canonical transaction data and did not broadcast live transactions${lifecycleText ? ` · ${lifecycleText}` : ''}.`,
      ok: true,
      status,
      reasonCode,
    };
  }

  return {
    headline: 'Wipe updated',
    detail: `Withdraw-everything returned status ${status || 'updated'}${lifecycleText ? ` · ${lifecycleText}` : ''}.`,
    ok,
    status: status || 'updated',
    reasonCode,
  };
}

function wipeControlBlockedDetail(reasonCode: string): string {
  const detailByReason: Record<string, string> = {
    withdraw_all_disabled: 'Withdraw-everything is blocked until the wipe control is explicitly enabled.',
    approved_destination_missing: 'Withdraw-everything is blocked until an approved destination is configured.',
    destination_not_allowlisted: 'Withdraw-everything is blocked because the approved destination is not on the backend allowlist.',
    executor_not_configured: 'Withdraw-everything is blocked because the executor is not configured.',
    invalid_executor_address: 'Withdraw-everything is blocked because the executor address is invalid.',
    capital_truth_degraded: 'Withdraw-everything is blocked because capital truth is degraded.',
    no_withdrawable_balance: 'Withdraw-everything is blocked because no withdrawable balance is currently available.',
    no_token_balances: 'Withdraw-everything is blocked because configured token balances are zero right now.',
    command_center_paused: 'Withdraw-everything is blocked while command center controls are paused.',
  };
  return detailByReason[reasonCode] ?? `Withdraw-everything is blocked · ${humanizeReason(reasonCode)}.`;
}

function wipePreviewBlockedDetail(reasonCode: string): string {
  const detailByReason: Record<string, string> = {
    withdraw_all_disabled: 'Last wipe preview was blocked until the wipe control is explicitly enabled.',
    approved_destination_missing: 'Last wipe preview was blocked until an approved destination is configured.',
    destination_not_allowlisted: 'Last wipe preview was blocked because the approved destination is not on the backend allowlist.',
    executor_not_configured: 'Last wipe preview was blocked because the executor is not configured.',
    invalid_executor_address: 'Last wipe preview was blocked because the executor address is invalid.',
    capital_truth_degraded: 'Last wipe preview was blocked because capital truth is degraded.',
    no_withdrawable_balance: 'Last wipe preview was blocked because no withdrawable balance is currently available.',
    no_token_balances: 'Last wipe preview found no token balances to withdraw right now.',
    command_center_paused: 'Last wipe preview was blocked while command center controls are paused.',
  };
  return detailByReason[reasonCode] ?? `Last wipe preview was blocked · ${humanizeReason(reasonCode)}.`;
}

function wipeExecuteBlockedDetail(reasonCode: string, result: Record<string, unknown> | null = null): string {
  if (reasonCode === 'preview_stale') {
    const currentReasonCode = text(result?.current_reason_code ?? '');
    if (currentReasonCode && currentReasonCode !== 'ok') {
      return `Last wipe execution was blocked because the persisted preview became stale after backend state changed (${humanizeReason(currentReasonCode)}); generate a fresh preview before retrying.`;
    }
    return 'Last wipe execution was blocked because the persisted preview became stale after backend state changed; generate a fresh preview before retrying.';
  }

  const detailByReason: Record<string, string> = {
    preview_id_mismatch: 'Last wipe execution was blocked because the preview id no longer matched persisted backend state.',
    confirmation_text_mismatch: 'Last wipe execution was blocked because the required confirmation text did not match.',
    preview_expired: 'Last wipe execution was blocked because the wipe preview expired; generate a fresh preview before retrying.',
    withdraw_execute_disabled_in_public_mode: 'Last wipe execution was blocked because live withdraw execution is disabled in public mode.',
    missing_private_key_env: 'Last wipe execution was blocked because the configured private key environment variable is missing.',
    invalid_private_key_env: 'Last wipe execution was blocked because the configured private key environment variable is invalid.',
    no_rpc_endpoints: 'Last wipe execution was blocked because the required read/send RPC endpoints were unavailable.',
    executor_not_configured: 'Last wipe execution was blocked because the executor is not configured.',
    invalid_executor_address: 'Last wipe execution was blocked because the executor address is invalid.',
    executor_owner_lookup_failed: 'Last wipe execution was blocked because executor owner proof could not be established from the read RPC.',
    executor_owner_mismatch: 'Last wipe execution was blocked because the configured signer is not the executor owner.',
  };
  return detailByReason[reasonCode] ?? `Last wipe execution was blocked · ${humanizeReason(reasonCode)}.`;
}

function summarizeWithdrawAllControlState(record: Record<string, unknown>): OffRampExecutionSummary | null {
  const controlStatus = text(record.status ?? '');
  const controlReasonCode = text(record.reason_code ?? record.control_reason_code ?? '');
  if (!controlStatus || controlStatus === 'idle') return null;

  if (controlStatus === 'available') {
    return {
      headline: 'Wipe ready',
      detail: 'Withdraw-everything control is available and ready for a fresh preview.',
      ok: true,
      status: controlStatus,
      reasonCode: controlReasonCode || 'ok',
    };
  }

  if (controlStatus === 'blocked') {
    return {
      headline: controlReasonCode === 'withdraw_all_disabled' ? 'Wipe disabled' : 'Wipe blocked',
      detail: wipeControlBlockedDetail(controlReasonCode),
      ok: false,
      status: controlStatus,
      reasonCode: controlReasonCode,
    };
  }

  if (controlStatus === 'degraded') {
    const detail = controlReasonCode === 'state_load_failed'
      ? 'Withdraw-everything state is degraded because persisted wipe state could not be loaded.'
      : `Withdraw-everything control is degraded · ${humanizeReason(controlReasonCode)}.`;
    return {
      headline: 'Wipe degraded',
      detail,
      ok: false,
      status: controlStatus,
      reasonCode: controlReasonCode,
    };
  }

  return {
    headline: `Wipe ${humanizeReason(controlStatus)}`,
    detail: `Withdraw-everything control returned status ${humanizeReason(controlStatus)}${controlReasonCode ? ` · ${humanizeReason(controlReasonCode)}` : ''}.`,
    ok: controlStatus !== 'unavailable',
    status: controlStatus,
    reasonCode: controlReasonCode,
  };
}

function shouldPreferCurrentWipeControlState(lastStatus: string, controlSummary: OffRampExecutionSummary | null): boolean {
  if (!controlSummary) return false;
  if (controlSummary.ok) return false;
  return lastStatus === 'preview_ready' || lastStatus === 'prepared';
}

export function summarizeWithdrawAllState(state: unknown): OffRampExecutionSummary | null {
  const record = asRecord(state);
  if (!record) return null;
  const lastStatus = text(record.last_status ?? '');
  const lastReasonCode = text(record.last_reason_code ?? '');
  const lastResult = asRecord(record.last_result);
  const lastResultSummary = asRecord(record.last_result_summary);
  const controlSummary = summarizeWithdrawAllControlState(record);

  if (!lastStatus || lastStatus === 'idle') {
    return controlSummary;
  }

  if (shouldPreferCurrentWipeControlState(lastStatus, controlSummary)) {
    return controlSummary;
  }

  if (lastStatus === 'execute_failed') {
    return summarizeWithdrawAllExecution({ ok: false, reason_code: lastReasonCode, result: lastResult ?? {}, last_result_summary: lastResultSummary ?? {} });
  }

  if (lastStatus === 'submitted' || lastStatus === 'completed') {
    return summarizeWithdrawAllExecution({ ok: true, result: { ...(lastResult ?? {}), status: text(lastResult?.status ?? lastStatus) }, last_result_summary: lastResultSummary ?? {} });
  }

  if (lastStatus === 'prepared') {
    return summarizeWithdrawAllExecution({ ok: true, result: { ...(lastResult ?? {}), status: 'prepared' }, last_result_summary: lastResultSummary ?? {} });
  }

  if (lastStatus === 'preview_ready') {
    const previewExpired = Boolean(record.preview_expired === true);
    return {
      headline: previewExpired ? 'Wipe preview expired' : 'Wipe preview ready',
      detail: previewExpired
        ? 'Last wipe preview expired; generate a fresh preview before triggering withdraw-everything again.'
        : 'Last wipe preview is ready for deliberate execution confirmation.',
      ok: !previewExpired,
      status: lastStatus,
      reasonCode: previewExpired ? 'preview_expired' : (lastReasonCode || 'ok'),
    };
  }

  if (lastStatus === 'preview_blocked') {
    return {
      headline: 'Wipe preview blocked',
      detail: wipePreviewBlockedDetail(lastReasonCode),
      ok: false,
      status: lastStatus,
      reasonCode: lastReasonCode,
    };
  }

  if (lastStatus === 'execute_blocked') {
    return {
      headline: 'Wipe blocked',
      detail: wipeExecuteBlockedDetail(lastReasonCode, lastResult),
      ok: false,
      status: lastStatus,
      reasonCode: lastReasonCode,
    };
  }

  const lifecycleText = lifecycleDetail(lastResultSummary);
  return {
    headline: `Wipe ${humanizeReason(lastStatus)}`,
    detail: `Last wipe status is ${humanizeReason(lastStatus)}${lifecycleText ? ` · ${lifecycleText}` : ''}.`,
    ok: lastStatus !== 'degraded',
    status: lastStatus,
    reasonCode: lastReasonCode,
  };
}
