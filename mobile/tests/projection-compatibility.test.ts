import test from 'node:test';
import { strict as assert } from 'node:assert';

import {
  evaluateProjectionCompatibility,
  mergeProjectionCompatibility,
  normalizeSummaryContract,
  projectionCompatibilityAlert,
} from '../src/commandCenter/projectionContract';

test('normalizeSummaryContract reads canonical summary contracts', () => {
  const out = normalizeSummaryContract({
    contractVersion: 'canonical_summary_read_contract_v1',
    truthFamily: 'command_center',
    readModel: 'command_center_summary_projection_v1',
  });
  assert.equal(out?.truthFamily, 'command_center');
  assert.equal(out?.readModel, 'command_center_summary_projection_v1');
});

test('evaluateProjectionCompatibility degrades on missing contract and surfaces fallback use', () => {
  const out = evaluateProjectionCompatibility(undefined, {
    truthFamily: 'fund',
    readModel: 'fund_summary_projection_v1',
    fallbackUsed: true,
  });
  assert.equal(out.status, 'degraded');
  assert.deepEqual(out.reasonCodes, ['summary_contract_missing', 'legacy_projection_fallback_used']);
});

test('evaluateProjectionCompatibility degrades on family mismatch', () => {
  const out = evaluateProjectionCompatibility(
    {
      contractVersion: 'canonical_summary_read_contract_v1',
      truthFamily: 'launch_family',
      readModel: 'launch_family_projection_v1',
    },
    {
      truthFamily: 'launch',
      readModel: 'launch_summary_projection_v1',
    },
  );
  assert.equal(out.status, 'degraded');
  assert.deepEqual(out.reasonCodes, [
    'summary_contract_truth_family_mismatch',
    'summary_contract_read_model_mismatch',
  ]);
});

test('mergeProjectionCompatibility produces prefixed reasons and alert payloads', () => {
  const merged = mergeProjectionCompatibility({
    commandCenter: evaluateProjectionCompatibility(undefined, {
      truthFamily: 'command_center',
      readModel: 'command_center_summary_projection_v1',
      fallbackUsed: true,
    }),
    launch: evaluateProjectionCompatibility(
      {
        contractVersion: 'canonical_summary_read_contract_v1',
        truthFamily: 'launch',
        readModel: 'launch_summary_projection_v1',
      },
      {
        truthFamily: 'launch',
        readModel: 'launch_summary_projection_v1',
      },
    ),
  });
  assert.equal(merged?.status, 'degraded');
  assert.deepEqual(merged?.reasonCodes, [
    'commandCenter:summary_contract_missing',
    'commandCenter:legacy_projection_fallback_used',
  ]);
  const alert = projectionCompatibilityAlert(merged, { tsMs: 42 });
  assert.equal(alert?.severity, 'danger');
  assert.match(String(alert?.detail), /commandCenter:summary_contract_missing/);
});
