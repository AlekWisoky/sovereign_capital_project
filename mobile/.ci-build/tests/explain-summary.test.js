"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const node_assert_1 = require("node:assert");
const executionSummary_1 = require("../src/commandCenter/executionSummary");
(0, node_test_1.default)('formatExplainResponse includes causal sections and alternatives', () => {
    const text = (0, executionSummary_1.formatExplainResponse)({
        ok: true,
        text: 'fallback',
        facts: {},
        causal: {
            whyRoute: 'best route',
            whySize: 'bounded size',
            whyLane: 'private lane',
            whyNow: 'half-life still positive',
            whyNot: [{ kind: 'route', candidate: 'curve', reason: 'lower EV' }],
            suppressionReasons: ['family:flashloan_atomic: fee_burn_rate'],
            routeInvalidCauses: ['leg:curve:invalid'],
            serviceSummary: {
                admission: { ok: true },
                execution: { ok: true },
                receipt: { ok: false },
                telemetry: { ok: true },
            },
        },
    });
    node_assert_1.strict.equal(text.includes('Why this route: best route'), true);
    node_assert_1.strict.equal(text.includes('route:curve (lower EV)'), true);
    node_assert_1.strict.equal(text.includes('Suppression reasons:'), true);
    node_assert_1.strict.equal(text.includes('Service health: admission:ok, execution:ok, receipt:degraded, telemetry:ok'), true);
});
