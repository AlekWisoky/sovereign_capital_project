import React, { useEffect, useMemo, useState } from "react";
import { View, Text, ScrollView, Pressable, TextInput } from "react-native";
import { useTheme } from "../../utils/useTheme";
import { pageContentContainerStyle, pageShellStyle } from '../../utils/layout';
import { BrandHeader } from "../../components/v2/BrandHeader";
import { SurfaceCard } from "../../components/v2/SurfaceCard";
import { ConfirmDialog } from "../../components/v2/ConfirmDialog";
import { ReceiptDrawer } from "../../components/v2/ReceiptDrawer";
import { useStore } from "../../state/store";
import { useTickets } from "../../state/ticketsContext";
import { loadAddressBook, saveAddressBook, type AddressBookEntry } from "../../state/addressBook";
import { withdrawConfig, withdrawPrepare, withdrawExecute } from "../../api/client";
import { summarizeWithdrawExecution } from "../../utils/offRampStatus";
import type { JsonValue } from "../../utils/types";
import { fmtShortHash } from "../../utils/format";

function asRecord(v: unknown): Record<string, unknown> | null {
  return typeof v === "object" && v !== null ? (v as Record<string, unknown>) : null;
}

function isAddress(s: string): boolean {
  const v = s.trim();
  return /^0x[0-9a-fA-F]{40}$/.test(v);
}

export function WalletScreen() {
  const theme = useTheme();
  const { state, session, setSession } = useStore();
  const { tickets } = useTickets();

  const [cfg, setCfg] = useState<Record<string, unknown>>({});
  const [token, setToken] = useState<string>("");
  const [to, setTo] = useState<string>("");
  const [amount, setAmount] = useState<string>("");
  const [prepared, setPrepared] = useState<Record<string, unknown> | null>(null);
  const [status, setStatus] = useState<string>("");
  const [confirmExec, setConfirmExec] = useState(false);
  const [drawer, setDrawer] = useState<{ open: boolean; title: string; payload?: JsonValue }>({ open: false, title: "" });

  const [book, setBook] = useState<AddressBookEntry[]>([]);
  const [newName, setNewName] = useState("");
  const [newAddr, setNewAddr] = useState("");

  const operator = state.role === "operator" && !session.locked;

  useEffect(() => {
    (async () => {
      const ab = await loadAddressBook();
      setBook(ab);
    })();
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const c = await withdrawConfig(state.baseUrl, state.role === "operator" ? state.adminKey : undefined);
        setCfg(c as Record<string, unknown>);
        const tokens = asRecord(c)?.["tokens"];
        if (Array.isArray(tokens) && tokens.length && !token) setToken(String(tokens[0]));
        const profitTo = asRecord(c)?.["profit_to"];
        if (typeof profitTo === "string" && !to) setTo(profitTo);
      } catch {
        // ignore
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.baseUrl]);

  const withdrawMode = String(asRecord(cfg)?.["withdraw_mode"] ?? "-");
  const tokens = useMemo(() => {
    const t = asRecord(cfg)?.["tokens"];
    return Array.isArray(t) ? t.map((x) => String(x)) : [];
  }, [cfg]);

  const recentTxs = useMemo(() => {
    const out: { id: string; tx?: string; strategy: string }[] = [];
    for (const t of tickets.slice(0, 12)) {
      const tr = asRecord(t.trade);
      const tx = typeof tr?.["tx_hash"] === "string" ? String(tr?.["tx_hash"]) : undefined;
      if (tx) out.push({ id: t.id, tx, strategy: t.strategy });
    }
    return out;
  }, [tickets]);

  async function addEntry() {
    if (!isAddress(newAddr)) {
      setStatus("Invalid address.");
      return;
    }
    const next = [{ name: newName.trim() || "Unnamed", address: newAddr.trim() }, ...book.filter((e) => e.address.toLowerCase() !== newAddr.trim().toLowerCase())];
    setBook(next);
    await saveAddressBook(next);
    setNewName("");
    setNewAddr("");
    setStatus("Saved to address book.");
  }

  async function doPrepare() {
    if (!operator) {
      setStatus("Locked/Read-only: unlock to prepare.");
      return;
    }
    if (!token || !isAddress(to) || !amount.trim()) {
      setStatus("Missing token / to / amount.");
      return;
    }
    setStatus("Preparing…");
    try {
      const res = await withdrawPrepare(
        state.baseUrl,
        {
          token,
          to,
          amount,
        },
        state.adminKey,
      );
      setPrepared(res as Record<string, unknown>);
      setStatus("Prepared.");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setStatus(`Prepare failed · ${msg}`);
    }
  }

  async function doExecute() {
    if (!operator) {
      setStatus("Locked/Read-only: unlock to execute.");
      return;
    }
    if (!session.armed) {
      setStatus("Not ARMED.");
      return;
    }
    if (!prepared) {
      setStatus("Prepare first.");
      return;
    }
    setConfirmExec(false);
    setStatus("Executing…");
    try {
      const res = await withdrawExecute(state.baseUrl, { token, to, amount }, state.adminKey);
      setDrawer({ open: true, title: "Withdraw Execute Result", payload: res as unknown as JsonValue });
      const summary = summarizeWithdrawExecution(res, "Withdraw");
      setStatus(summary.detail);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setStatus(`Execute failed · ${msg}`);
    }
  }

  const rightTag = `${state.role === "operator" ? (session.locked ? "LOCKED" : session.armed ? "ARMED" : "SAFE") : "READ"} · ${withdrawMode.toUpperCase()}`;

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 24)}>
      <BrandHeader title="Wallet" subtitle="Withdraw + address book" rightTag={rightTag} />

      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Address Book</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>Fast, safe destination selection with human handling.</Text>

        <View style={{ marginTop: theme.spacing.md }}>
          {book.slice(0, 8).map((e) => (
            <Pressable
              key={e.address}
              onPress={() => setTo(e.address)}
              style={{
                paddingVertical: 10,
                borderTopWidth: 1,
                borderTopColor: theme.colors.border,
                flexDirection: "row",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <View style={{ flex: 1, paddingRight: 10 }}>
                <Text style={{ color: theme.colors.text, fontWeight: "900" }}>{e.name}</Text>
                <Text style={{ color: theme.colors.textFaint, marginTop: 4, fontFamily: "monospace" }}>{e.address}</Text>
              </View>
              <Text style={{ color: theme.colors.cyan, fontWeight: "900" }}>Use</Text>
            </Pressable>
          ))}
        </View>

        <View style={{ flexDirection: "row", gap: 10, marginTop: theme.spacing.md }}>
          <TextInput
            value={newName}
            onChangeText={setNewName}
            placeholder="Name"
            placeholderTextColor={theme.colors.textFaint}
            style={{ flex: 1, padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, color: theme.colors.text, backgroundColor: theme.colors.surface1 }}
          />
          <TextInput
            value={newAddr}
            onChangeText={setNewAddr}
            placeholder="0x…"
            placeholderTextColor={theme.colors.textFaint}
            autoCapitalize="none"
            autoCorrect={false}
            style={{ flex: 2, padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, color: theme.colors.text, backgroundColor: theme.colors.surface1, fontFamily: "monospace" }}
          />
        </View>

        <Pressable
          onPress={() => void addEntry()}
          style={{ marginTop: 10, paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface2, alignItems: "center" }}
        >
          <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>Add</Text>
        </Pressable>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />

      <SurfaceCard glow="cyan">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Withdraw</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>Preserves config → prepare → execute flow, restyled for the new theme.</Text>

        <View style={{ marginTop: theme.spacing.md }}>
          <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Token</Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
            {(tokens.length ? tokens : [token || "-"]).slice(0, 10).map((t) => {
              const active = t === token;
              return (
                <Pressable
                  key={t}
                  onPress={() => setToken(t)}
                  style={{
                    paddingHorizontal: 10,
                    paddingVertical: 8,
                    borderRadius: theme.radii.pill,
                    borderWidth: 1,
                    borderColor: active ? theme.colors.cyan : theme.colors.border,
                    backgroundColor: active ? theme.colors.surface2 : theme.colors.surface1,
                  }}
                >
                  <Text style={{ color: active ? theme.colors.text : theme.colors.textMuted, ...theme.typography.mono }}>{t}</Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>To</Text>
          <TextInput
            value={to}
            onChangeText={setTo}
            placeholder="0x…"
            placeholderTextColor={theme.colors.textFaint}
            autoCapitalize="none"
            autoCorrect={false}
            style={{ marginTop: 8, padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, color: theme.colors.text, backgroundColor: theme.colors.surface1, fontFamily: "monospace" }}
          />
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Amount</Text>
          <TextInput
            value={amount}
            onChangeText={setAmount}
            placeholder="wei"
            placeholderTextColor={theme.colors.textFaint}
            keyboardType="numeric"
            style={{ marginTop: 8, padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, color: theme.colors.text, backgroundColor: theme.colors.surface1, fontFamily: "monospace" }}
          />
        </View>

        <View style={{ flexDirection: "row", gap: 10, marginTop: theme.spacing.lg }}>
          <Pressable
            onPress={() => setSession({ armed: !session.armed })}
            disabled={state.role !== "operator" || session.locked}
            style={{
              flex: 1,
              paddingVertical: 12,
              borderRadius: theme.radii.md,
              borderWidth: 1,
              borderColor: session.armed ? theme.colors.good : theme.colors.border,
              backgroundColor: session.armed ? theme.colors.surface2 : theme.colors.surface1,
              alignItems: "center",
              opacity: state.role === "operator" && !session.locked ? 1 : 0.5,
            }}
          >
            <Text style={{ color: session.armed ? theme.colors.good : theme.colors.textMuted, fontWeight: "900" }}>{session.armed ? "ARMED" : "ARM"}</Text>
          </Pressable>

          <Pressable
            onPress={() => void doPrepare()}
            style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.violet, alignItems: "center", opacity: operator ? 1 : 0.5 }}
            disabled={!operator}
          >
            <Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>Prepare</Text>
          </Pressable>
        </View>

        <Pressable
          onPress={() => setConfirmExec(true)}
          disabled={!operator || !session.armed || !prepared}
          style={{
            marginTop: 10,
            paddingVertical: 12,
            borderRadius: theme.radii.md,
            backgroundColor: theme.colors.cyan,
            alignItems: "center",
            opacity: operator && session.armed && prepared ? 1 : 0.5,
          }}
        >
          <Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>Execute</Text>
        </Pressable>

        {prepared ? (
          <Pressable
            onPress={() => setDrawer({ open: true, title: "Prepared TX", payload: prepared as unknown as JsonValue })}
            style={{ marginTop: 10, paddingVertical: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1, alignItems: "center" }}
          >
            <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>View prepared tx</Text>
          </Pressable>
        ) : null}

        {status ? <Text style={{ color: theme.colors.textMuted, marginTop: theme.spacing.md, ...theme.typography.mono }}>{status}</Text> : null}
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />

      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>TX Visibility</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>Links into Ledger ticket history.</Text>

        {recentTxs.length ? (
          <View style={{ marginTop: theme.spacing.md }}>
            {recentTxs.map((t) => (
              <Pressable
                key={t.id}
                onPress={() => setDrawer({ open: true, title: `Ticket ${t.id}`, payload: tickets.find((x) => x.id === t.id) as unknown as JsonValue })}
                style={{ paddingVertical: 10, borderTopWidth: 1, borderTopColor: theme.colors.border }}
              >
                <Text style={{ color: theme.colors.text, fontWeight: "900" }}>{t.strategy}</Text>
                <Text style={{ color: theme.colors.textFaint, marginTop: 4, fontFamily: "monospace" }}>{fmtShortHash(String(t.tx), 10)}</Text>
              </Pressable>
            ))}
          </View>
        ) : (
          <Text style={{ color: theme.colors.textFaint, marginTop: theme.spacing.md, ...theme.typography.mono }}>(no tx yet)</Text>
        )}
      </SurfaceCard>

      <ConfirmDialog
        visible={confirmExec}
        title="Execute withdraw?"
        body={`Mode: ${withdrawMode}\n\nThis will initiate a withdraw transaction.\n\nNo hold-to-confirm: tap-based confirmation.`}
        confirmText="Execute"
        cancelText="Cancel"
        tone="danger"
        onCancel={() => setConfirmExec(false)}
        onConfirm={() => void doExecute()}
      />

      <ReceiptDrawer visible={drawer.open} title={drawer.title} payload={drawer.payload} onClose={() => setDrawer({ open: false, title: "" })} />
    </ScrollView>
  );
}
