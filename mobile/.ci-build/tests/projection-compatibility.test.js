"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const node_assert_1 = require("node:assert");
const projectionContract_1 = require("../src/commandCenter/projectionContract");
(0, node_test_1.default)('normalizeSummaryContract reads canonical summary contracts', () => {
    const out = (0, projectionContract_1.normalizeSummaryContract)({
        contractVersion: 'canonical_summary_read_contract_v1',
        truthFamily: 'command_center',
        readModel: 'command_center_summary_projection_v1',
    });
    node_assert_1.strict.equal(out?.truthFamily, 'command_center');
    node_assert_1.strict.equal(out?.readModel, 'command_center_summary_projection_v1');
});
(0, node_test_1.default)('evaluateProjectionCompatibility degrades on missing contract and surfaces fallback use', () => {
    const out = (0, projectionContract_1.evaluateProjectionCompatibility)(undefined, {
        truthFamily: 'fund',
        readModel: 'fund_summary_projection_v1',
        fallbackUsed: true,
    });
    node_assert_1.strict.equal(out.status, 'degraded');
    node_assert_1.strict.deepEqual(out.reasonCodes, ['summary_contract_missing', 'legacy_projection_fallback_used']);
});
(0, node_test_1.default)('evaluateProjectionCompatibility degrades on family mismatch', () => {
    const out = (0, projectionContract_1.evaluateProjectionCompatibility)({
        contractVersion: 'canonical_summary_read_contract_v1',
        truthFamily: 'launch_family',
        readModel: 'launch_family_projection_v1',
    }, {
        truthFamily: 'launch',
        readModel: 'launch_summary_projection_v1',
    });
    node_assert_1.strict.equal(out.status, 'degraded');
    node_assert_1.strict.deepEqual(out.reasonCodes, [
        'summary_contract_truth_family_mismatch',
        'summary_contract_read_model_mismatch',
    ]);
});
(0, node_test_1.default)('mergeProjectionCompatibility produces prefixed reasons and alert payloads', () => {
    const merged = (0, projectionContract_1.mergeProjectionCompatibility)({
        commandCenter: (0, projectionContract_1.evaluateProjectionCompatibility)(undefined, {
            truthFamily: 'command_center',
            readModel: 'command_center_summary_projection_v1',
            fallbackUsed: true,
        }),
        launch: (0, projectionContract_1.evaluateProjectionCompatibility)({
            contractVersion: 'canonical_summary_read_contract_v1',
            truthFamily: 'launch',
            readModel: 'launch_summary_projection_v1',
        }, {
            truthFamily: 'launch',
            readModel: 'launch_summary_projection_v1',
        }),
    });
    node_assert_1.strict.equal(merged?.status, 'degraded');
    node_assert_1.strict.deepEqual(merged?.reasonCodes, [
        'commandCenter:summary_contract_missing',
        'commandCenter:legacy_projection_fallback_used',
    ]);
    const alert = (0, projectionContract_1.projectionCompatibilityAlert)(merged, { tsMs: 42 });
    node_assert_1.strict.equal(alert?.severity, 'danger');
    node_assert_1.strict.match(String(alert?.detail), /commandCenter:summary_contract_missing/);
});
