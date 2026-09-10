import React from 'react';
import { ScrollView, Text, View } from 'react-native';
import { useTheme } from '../utils/useTheme';
import { pageContentContainerStyle, pageShellStyle } from '../utils/layout';
import { SurfaceCard } from '../components/v2/SurfaceCard';
import { useStore } from '../state/store';
import { useCanonicalFeed } from '../domain/useCanonicalFeed';

export function CanonicalActivityScreen() {
  const theme = useTheme();
  const { state } = useStore();
  const feed = useCanonicalFeed(state.baseUrl, state.role === 'operator' ? state.adminKey : undefined, state.ccRefreshMs ?? 4500);
  const transactions = feed.snapshot?.activity.transactions ?? [];
  const liveTrades = feed.snapshot?.activity.liveTrades ?? [];

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 40)}>
      <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Activity</Text>
      <Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>Live trades, transaction history, providers, receipts, settlement and realized economics.</Text>
      <View style={{ marginTop: 12, padding: 10, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
        <Text style={{ color: theme.colors.text, fontWeight: '900' }}>{feed.freshness.toUpperCase()} · {liveTrades.length} live/pending</Text>
        <Text style={{ color: theme.colors.textFaint, marginTop: 4 }}>{feed.error || `${transactions.length} canonical ledger transactions loaded`}</Text>
      </View>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="cyan">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Live trades</Text>
        {liveTrades.length === 0 ? <Text style={{ color: theme.colors.textMuted, marginTop: 8 }}>No unsettled submitted transactions are currently visible in the canonical ledger.</Text> : liveTrades.map((trade, index) => (
          <TradeRow key={trade.transactionId ?? trade.txHash ?? String(index)} trade={trade} theme={theme} />
        ))}
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Transaction history</Text>
        {transactions.length === 0 ? <Text style={{ color: theme.colors.textMuted, marginTop: 8 }}>No transactions returned by the backend ledger projection.</Text> : transactions.map((tx, index) => (
          <TradeRow key={tx.transactionId ?? tx.txHash ?? String(index)} trade={tx} theme={theme} />
        ))}
      </SurfaceCard>
    </ScrollView>
  );
}

function TradeRow({ trade, theme }: { trade: any; theme: ReturnType<typeof useTheme> }) {
  const pnl = trade.signedPnlUsd ?? trade.realizedNetProfitUsd;
  return (
    <View style={{ marginTop: 10, padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
        <Text style={{ color: theme.colors.text, fontWeight: '900', flex: 1 }}>{trade.family ?? 'trade'} · {trade.route ?? 'route unavailable'}</Text>
        <Text style={{ color: pnl == null ? theme.colors.textFaint : pnl >= 0 ? theme.colors.success : theme.colors.danger, fontWeight: '900' }}>{pnl == null ? 'P&L —' : `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`}</Text>
      </View>
      <Text style={{ color: theme.colors.textFaint, marginTop: 5 }}>Provider: {trade.provider ?? 'not reported'} · status: {String(trade.status ?? 'unknown')} · settlement: {trade.settlementVerified ? 'verified' : 'pending/unverified'}</Text>
      <Text style={{ color: theme.colors.textFaint, marginTop: 5 }}>tx: {trade.txHash ?? trade.transactionId ?? 'not reported'}</Text>
      <Text style={{ color: theme.colors.textFaint, marginTop: 5 }}>decision: {trade.decisionId ?? '—'} · execution: {trade.executionId ?? '—'} · receipt: {trade.receiptId ?? '—'}</Text>
    </View>
  );
}
