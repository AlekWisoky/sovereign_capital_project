import React, { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, View } from 'react-native';
import { RouteProp, useRoute } from '@react-navigation/native';
import { useTheme } from '../utils/useTheme';
import { pageContentContainerStyle, pageShellStyle } from '../utils/layout';
import { SurfaceCard } from '../components/v2/SurfaceCard';
import { getXaiDecision } from '../api/canonical';
import type { DecisionSnapshot } from '../domain/canonical';
import { useStore } from '../state/store';

export type DecisionDetailRouteParams = { DecisionDetail: { decisionId: string } };

type Route = RouteProp<DecisionDetailRouteParams, 'DecisionDetail'>;

export function CanonicalDecisionDetailScreen() {
  const theme = useTheme();
  const route = useRoute<Route>();
  const { state } = useStore();
  const [decision, setDecision] = useState<DecisionSnapshot | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    void getXaiDecision(state.baseUrl, route.params.decisionId, state.role === 'operator' ? state.adminKey : undefined)
      .then((value) => { if (active) setDecision(value); })
      .catch((value: unknown) => { if (active) setError(value instanceof Error ? value.message : String(value)); });
    return () => { active = false; };
  }, [route.params.decisionId, state.adminKey, state.baseUrl, state.role]);

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 40)}>
      <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Canonical Decision</Text>
      <Text style={{ color: theme.colors.textFaint, marginTop: 6, ...theme.typography.mono }}>{route.params.decisionId}</Text>
      {error ? <Text style={{ color: theme.colors.danger, marginTop: 12 }}>{error}</Text> : null}
      {!decision && !error ? <View style={{ padding: 24, alignItems: 'center' }}><ActivityIndicator /></View> : null}
      {decision ? (
        <>
          <View style={{ height: theme.spacing.md }} />
          <SurfaceCard glow="cyan">
            <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>{decision.action ?? 'decision'} · {decision.strategyFamily ?? 'unknown family'}</Text>
            <Text style={{ color: theme.colors.textMuted, marginTop: 8 }}>Expected net: {decision.expectedNetProfitUsd == null ? '—' : `$${decision.expectedNetProfitUsd.toFixed(2)}`} · ROI: {decision.expectedRoiPct == null ? '—' : `${decision.expectedRoiPct.toFixed(2)}%`}</Text>
            <Text style={{ color: theme.colors.textMuted, marginTop: 5 }}>Required capital: {decision.requiredCapitalUsd == null ? '—' : `$${decision.requiredCapitalUsd.toLocaleString()}`} · p(success): {decision.pSuccess == null ? '—' : `${(decision.pSuccess * 100).toFixed(1)}%`}</Text>
          </SurfaceCard>

          <View style={{ height: theme.spacing.md }} />
          <SurfaceCard glow="none">
            <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Canonical lineage</Text>
            {[
              ['decision_id', decision.decisionId],
              ['correlation_id', decision.correlationId],
              ['execution_id', decision.executionId],
              ['receipt_id', decision.receiptId],
              ['outcome_id', decision.outcomeId],
              ['sizing_id', decision.sizingId],
              ['opportunity_id', decision.opportunityId],
              ['route_id', decision.routeId],
            ].map(([label, value]) => <Line key={label} label={label} value={value} theme={theme} />)}
          </SurfaceCard>

          <View style={{ height: theme.spacing.md }} />
          <SurfaceCard glow="none">
            <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Admission → execution → settlement</Text>
            <Line label="governance" value={decision.governanceAllowed == null ? '—' : decision.governanceAllowed ? 'allowed' : 'blocked'} theme={theme} />
            <Line label="admission" value={decision.admissionAllowed == null ? '—' : decision.admissionAllowed ? 'allowed' : 'blocked'} theme={theme} />
            <Line label="borrow" value={decision.proposedBorrowAmount ?? '—'} theme={theme} />
            <Line label="size multiplier" value={decision.sizeMult == null ? '—' : `${decision.sizeMult.toFixed(2)}x`} theme={theme} />
            <Line label="borrow multiplier" value={decision.borrowMult == null ? '—' : `${decision.borrowMult.toFixed(2)}x`} theme={theme} />
            <Line label="settlement" value={decision.settlementVerified == null ? '—' : decision.settlementVerified ? 'verified' : 'not verified'} theme={theme} />
            <Line label="realized net" value={decision.realizedNetProfitUsd == null ? '—' : `$${decision.realizedNetProfitUsd.toFixed(2)}`} theme={theme} />
            <Line label="expectation error" value={decision.expectationErrorUsd == null ? '—' : `$${decision.expectationErrorUsd.toFixed(2)}`} theme={theme} />
            <Line label="OMAR learning" value={decision.learningRecorded == null ? '—' : decision.learningRecorded ? 'recorded' : 'not recorded'} theme={theme} />
          </SurfaceCard>
        </>
      ) : null}
    </ScrollView>
  );
}

function Line({ label, value, theme }: { label: string; value: unknown; theme: ReturnType<typeof useTheme> }) {
  return <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: theme.colors.border }}><Text style={{ color: theme.colors.textFaint }}>{label}</Text><Text style={{ color: theme.colors.text, fontWeight: '800', flex: 1, textAlign: 'right' }}>{String(value ?? '—')}</Text></View>;
}
