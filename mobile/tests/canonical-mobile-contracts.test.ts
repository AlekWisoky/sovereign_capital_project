import test from 'node:test';
import { strict as assert } from 'node:assert';

import type { DecisionDetail, TransactionRecord } from '../src/contracts/canonical';

function decisionLineage(detail: DecisionDetail): string[] {
  return [detail.decisionId, detail.opportunityId, detail.executionId, detail.receiptId, detail.transactionId, detail.outcomeId]
    .filter((value): value is string => Boolean(value));
}

test('canonical decision detail preserves one authoritative decision identity', () => {
  const detail: DecisionDetail = {
    decisionId: 'dec-1',
    opportunityId: 'opp-1',
    executionId: 'exec-1',
    receiptId: 'receipt-1',
    transactionId: 'tx-1',
    outcomeId: 'outcome-1',
    settlementVerified: true,
    expectedNetUsd: 100,
    realizedNetUsd: 70,
    expectationErrorUsd: -30,
  };
  assert.equal(detail.decisionId, 'dec-1');
  assert.equal(detail.settlementVerified, true);
  assert.equal(detail.expectationErrorUsd, detail.realizedNetUsd! - detail.expectedNetUsd!);
  assert.equal(new Set(decisionLineage(detail)).size, decisionLineage(detail).length);
});

test('transaction history contract exposes provider, venue and canonical lineage fields', () => {
  const tx: TransactionRecord = {
    transactionId: 'tx-1',
    receiptId: 'receipt-1',
    txHash: '0xabc',
    provider: 'aave',
    venue: 'uniswap',
    chain: 'ethereum',
    lane: 'private',
    decisionId: 'dec-1',
    realizedNetUsd: 12.5,
    gasCostUsd: 1.2,
    borrowCostUsd: 0.5,
  };
  assert.equal(tx.provider, 'aave');
  assert.equal(tx.venue, 'uniswap');
  assert.equal(tx.decisionId, 'dec-1');
});
