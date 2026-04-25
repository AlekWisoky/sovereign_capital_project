import test from 'node:test';
import { strict as assert } from 'node:assert';
import { formatExplainResponse } from '../src/commandCenter/executionSummary';

test('formatExplainResponse includes causal sections and alternatives', () => {
  const text = formatExplainResponse({
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
  assert.equal(text.includes('Why this route: best route'), true);
  assert.equal(text.includes('route:curve (lower EV)'), true);
  assert.equal(text.includes('Suppression reasons:'), true);
  assert.equal(text.includes('Service health: admission:ok, execution:ok, receipt:degraded, telemetry:ok'), true);
});
