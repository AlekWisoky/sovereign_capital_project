import React, { useMemo, useState } from "react";
import { View, Text, ScrollView, Pressable } from "react-native";
import { useTheme } from "../../utils/useTheme";
import { pageContentContainerStyle, pageShellStyle } from '../../utils/layout';
import { BrandHeader } from "../../components/v2/BrandHeader";
import { SurfaceCard } from "../../components/v2/SurfaceCard";
import { TicketStepper } from "../../components/v2/TicketStepper";
import { ReceiptDrawer } from "../../components/v2/ReceiptDrawer";
import { JsonImportDialog } from "../../components/v2/JsonImportDialog";
import { fmtShortHash, fmtTime } from "../../utils/format";
import { shareText } from "../../utils/share";
import { useTickets } from "../../state/ticketsContext";
import type { TradeTicket } from "../../state/tickets";
import type { JsonValue } from "../../utils/types";

function stageTone(stage: TradeTicket["stage"], theme: ReturnType<typeof useTheme>): { color: string; label: string } {
  if (stage === "FAILED") return { color: theme.colors.danger, label: "FAILED" };
  if (stage === "DECODED") return { color: theme.colors.good, label: "DECODED" };
  if (stage === "EXEC_SENT" || stage === "MINED") return { color: theme.colors.warn, label: stage };
  return { color: theme.colors.textMuted, label: stage };
}

export function LedgerScreen() {
  const theme = useTheme();
  const { tickets, clear, upsert } = useTickets();
  const [selected, setSelected] = useState<TradeTicket | null>(tickets[0] ?? null);
  const [drawer, setDrawer] = useState<{ open: boolean; title: string; payload?: JsonValue }>({ open: false, title: "" });
  const [importOpen, setImportOpen] = useState(false);

  const latest = tickets[0] ?? null;
  const sel = selected ? tickets.find((t) => t.id === selected.id) ?? selected : latest;

  const activity = useMemo(() => tickets.slice(0, 20), [tickets]);

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 24)}>
      <BrandHeader title="Ledger" subtitle="Receipts-first audit trail" rightTag={`${tickets.length} tickets`} />

      <SurfaceCard glow="violet">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Ledger Hub</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Tickets are auditable objects that can be exported/restored. Local history stores non-secrets only.
        </Text>

        {sel ? (
          <View style={{ marginTop: theme.spacing.md }}>
            <Text style={{ color: theme.colors.textMuted, ...theme.typography.mono }}>Latest ticket</Text>
            <Text style={{ color: theme.colors.text, marginTop: 4, fontFamily: "monospace" }}>{sel.strategy}</Text>
            <Text style={{ color: theme.colors.textFaint, marginTop: 4, ...theme.typography.mono }}>
              {fmtTime(sel.createdAt)} · {fmtShortHash(sel.oppId, 6)}
            </Text>
            <TicketStepper stage={sel.stage} />

            <View style={{ flexDirection: "row", gap: 10, marginTop: theme.spacing.md }}>
              <Pressable
                onPress={() => {
                  const payload = JSON.stringify(sel, null, 2);
                  void shareText('x∆v Ticket JSON', payload);
                }}
                style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.cyan, alignItems: "center" }}
              >
                <Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>Share JSON</Text>
              </Pressable>
              <Pressable
                onPress={() => setDrawer({ open: true, title: "Receipt Drawer", payload: sel.decoded ?? sel.receipt ?? sel.trade ?? sel.simulate ?? (sel as unknown as JsonValue) })}
                style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1, alignItems: "center" }}
              >
                <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>Receipt</Text>
              </Pressable>
            </View>
          </View>
        ) : (
          <Text style={{ color: theme.colors.textFaint, marginTop: theme.spacing.md, ...theme.typography.mono }}>(no tickets yet)</Text>
        )}
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />

      <SurfaceCard glow="none">
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Recent Activity</Text>
          <View style={{ flexDirection: "row", gap: 10 }}>
            <Pressable
              onPress={() => setImportOpen(true)}
              style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: theme.radii.pill, backgroundColor: theme.colors.surface2, borderWidth: 1, borderColor: theme.colors.border }}
            >
              <Text style={{ color: theme.colors.cyan, fontWeight: "900" }}>Import</Text>
            </Pressable>
            <Pressable
              onPress={() => void clear()}
              style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: theme.radii.pill, backgroundColor: theme.colors.surface2, borderWidth: 1, borderColor: theme.colors.border }}
            >
              <Text style={{ color: theme.colors.danger, fontWeight: "900" }}>Clear</Text>
            </Pressable>
          </View>
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          {activity.map((t) => {
            const tone = stageTone(t.stage, theme);
            return (
              <Pressable
                key={t.id}
                onPress={() => setSelected(t)}
                style={{
                  paddingVertical: 12,
                  borderTopWidth: 1,
                  borderTopColor: theme.colors.border,
                  flexDirection: "row",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <View style={{ flex: 1, paddingRight: 10 }}>
                  <Text style={{ color: theme.colors.text, fontWeight: "900" }}>{t.strategy}</Text>
                  <Text style={{ color: theme.colors.textFaint, marginTop: 4, ...theme.typography.mono }}>{fmtTime(t.createdAt)} · {fmtShortHash(t.oppId, 5)}</Text>
                </View>
                <View style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: theme.radii.pill, borderWidth: 1, borderColor: theme.colors.border }}>
                  <Text style={{ color: tone.color, ...theme.typography.mono }}>{tone.label}</Text>
                </View>
              </Pressable>
            );
          })}
        </View>
      </SurfaceCard>

      <ReceiptDrawer visible={drawer.open} title={drawer.title} payload={drawer.payload} onClose={() => setDrawer({ open: false, title: "" })} />

      <JsonImportDialog
        visible={importOpen}
        onClose={() => setImportOpen(false)}
        onImport={(text) => {
          try {
            const parsed = JSON.parse(text) as unknown;
            if (typeof parsed !== "object" || parsed === null) throw new Error("Not an object");
            const o = parsed as Record<string, unknown>;
            const id = typeof o.id === "string" ? o.id : "";
            const oppId = typeof o.oppId === "string" ? o.oppId : "";
            const strategy = typeof o.strategy === "string" ? o.strategy : "";
            const chain = typeof o.chain === "string" ? o.chain : "";
            const createdAt = typeof o.createdAt === "number" ? o.createdAt : Date.now();
            const stage = typeof o.stage === "string" ? (o.stage as TradeTicket["stage"]) : "NEW";
            if (!id || !oppId || !strategy || !chain) throw new Error("Missing required fields");
            const ticket: TradeTicket = {
              id,
              oppId,
              strategy,
              chain,
              createdAt,
              stage,
              amountInOverride: typeof o.amountInOverride === "string" ? o.amountInOverride : undefined,
              simulate: (o.simulate as JsonValue | undefined) ?? undefined,
              trade: (o.trade as JsonValue | undefined) ?? undefined,
              receipt: (o.receipt as JsonValue | undefined) ?? undefined,
              decoded: (o.decoded as JsonValue | undefined) ?? undefined,
            };
            void upsert(ticket);
            setSelected(ticket);
            setImportOpen(false);
          } catch {
            // ignore; user can retry
          }
        }}
      />
    </ScrollView>
  );
}
