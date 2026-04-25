import React, { useEffect, useMemo, useState } from "react";
import { View, Text, ScrollView, Pressable, TextInput } from "react-native";
import { useTheme } from "../../utils/useTheme";
import { pageContentContainerStyle, pageShellStyle } from '../../utils/layout';
import { TopStatusBar } from "../../components/cc/TopStatusBar";
import { SurfaceCard } from "../../components/v2/SurfaceCard";
import { SegmentedTabs } from "../../components/v2/SegmentedTabs";
import { ConfirmDialog } from "../../components/v2/ConfirmDialog";
import { ReceiptDrawer } from "../../components/v2/ReceiptDrawer";
import { ConfirmReasonDialog } from "../../components/cc/ConfirmReasonDialog";
import { useStore } from "../../state/store";
import { withdrawConfig, withdrawPrepare, withdrawExecute, convertWithdrawQuote, convertWithdrawPrepare, convertWithdrawExecute, withdrawAllState, withdrawAllConfig, withdrawAllPreview, withdrawAllExecute } from "../../api/client";
import { describeWithdrawAllRefresh, describeWithdrawAllRefreshWarning, nextWithdrawAllRefreshDelayMs, shouldAutoRefreshWithdrawAllState, summarizeWithdrawExecution, summarizeWithdrawAllExecution, summarizeWithdrawAllState } from "../../utils/offRampStatus";
import type { JsonValue } from "../../utils/types";

function asRecord(v: unknown): Record<string, unknown> | null {
  return typeof v === "object" && v !== null ? (v as Record<string, unknown>) : null;
}

function isAddress(s: string): boolean {
  const v = s.trim();
  return /^0x[0-9a-fA-F]{40}$/.test(v);
}

type Quote = {
  ok: boolean;
  expected_out?: string;
  min_out?: string;
  fee?: number;
  slippage_bps?: number;
  token_out?: string;
  reason?: string;
};

export function OffRampScreen() {
  const theme = useTheme();
  const { state, session, set } = useStore();

  const operator = state.role === "operator" && !session.locked;

  const [tab, setTab] = useState<"Convert" | "Withdraw">("Convert");

  const [cfg, setCfg] = useState<Record<string, unknown>>({});
  const [status, setStatus] = useState<string>("");
  const [drawer, setDrawer] = useState<{ open: boolean; title: string; payload?: JsonValue }>({ open: false, title: "" });

  // Convert flow
  const [tokenIn, setTokenIn] = useState<string>("");
  const [stableOut, setStableOut] = useState<"USDC" | "USDT">("USDC");
  const [amountIn, setAmountIn] = useState<string>("");
  const [dest, setDest] = useState<string>("");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [confirmConvertExec, setConfirmConvertExec] = useState(false);
  const [confirmReason, setConfirmReason] = useState(false);

  // Direct withdraw flow
  const [wToken, setWToken] = useState<string>("");
  const [wAmount, setWAmount] = useState<string>("");
  const [confirmWithdrawExec, setConfirmWithdrawExec] = useState(false);
  const [prepared, setPrepared] = useState<Record<string, unknown> | null>(null);
  const [saveRecipientOnConfirm, setSaveRecipientOnConfirm] = useState<boolean>(true);
  const [confirmEveryCashOut, setConfirmEveryCashOut] = useState<boolean>(true);
  const [wipeState, setWipeState] = useState<Record<string, unknown>>({});
  const [wipeDestination, setWipeDestination] = useState<string>("");
  const [confirmWipeExec, setConfirmWipeExec] = useState(false);
  const [wipeLastRefreshAtMs, setWipeLastRefreshAtMs] = useState<number>(0);
  const [wipeRefreshError, setWipeRefreshError] = useState<string>("");

  const withdrawMode = String(asRecord(cfg)?.["withdraw_mode"] ?? "txdata");

  const tokens = useMemo(() => {
    const t = asRecord(cfg)?.["tokens"];
    return Array.isArray(t) ? t.map((x) => String(x)) : [];
  }, [cfg]);

  const stables = useMemo(() => {
    const s = asRecord(cfg)?.["stables"];
    return asRecord(s) ?? {};
  }, [cfg]);

  useEffect(() => {
    (async () => {
      try {
        const c = await withdrawConfig(state.baseUrl, state.role === "operator" ? state.adminKey : undefined);
        setCfg(c as Record<string, unknown>);

        const t = asRecord(c)?.["tokens"];
        if (Array.isArray(t) && t.length) {
          if (!tokenIn) setTokenIn(String(t[0]));
          if (!wToken) setWToken(String(t[0]));
        }
        const profitTo = asRecord(c)?.["profit_to"];
        if (typeof profitTo === "string" && !dest) setDest(profitTo);
        const wipe = await withdrawAllState(state.baseUrl, state.role === "operator" ? state.adminKey : undefined);
        setWipeState(wipe as Record<string, unknown>);
        setWipeLastRefreshAtMs(Date.now());
        setWipeRefreshError("");
        const wipeRecord = asRecord(wipe) ?? {};
        const approved = wipeRecord["approved_destination"];
        const pending = wipeRecord["pending_destination"];
        const candidate = typeof approved === "string" && approved ? approved : typeof pending === "string" ? pending : "";
        if (candidate) setWipeDestination(candidate);
      } catch (e: unknown) {
        setStatus(e instanceof Error ? e.message : String(e));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.baseUrl]);

  const rightTag = `${state.role === "operator" ? (session.locked ? "LOCKED" : session.armed ? "ARMED" : "SAFE") : "READ"} · ${withdrawMode.toUpperCase()}`;

  async function doQuote() {
    if (!operator) {
      setStatus("Locked/Read-only: unlock to quote.");
      return;
    }
    if (!tokenIn || !amountIn.trim()) {
      setStatus("Missing token/amount.");
      return;
    }
    setStatus("Quoting…");
    setQuote(null);
    try {
      const res = (await convertWithdrawQuote(
        state.baseUrl,
        {
          token_in: tokenIn,
          token_out: stableOut,
          amount_in: amountIn,
          slippage_bps: state.slippageBps,
          fee_tiers: [500, 3000, 10000],
        },
        state.adminKey,
      )) as any;
      setQuote(res as Quote);
      setStatus(res?.ok ? "Quote ready." : `Quote failed · ${String(res?.reason ?? res?.error ?? "unknown")}`);
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  async function doConvertPrepare() {
    if (!operator) {
      setStatus("Locked/Read-only: unlock to prepare.");
      return;
    }
    if (!tokenIn || !amountIn.trim() || !isAddress(dest)) {
      setStatus("Missing token/amount/destination.");
      return;
    }
    if (!quote?.ok) {
      setStatus("Quote first (computes minOut).");
      return;
    }
    setStatus("Preparing…");
    try {
      const res = await convertWithdrawPrepare(
        state.baseUrl,
        {
          token_in: tokenIn,
          token_out: stableOut,
          amount_in: amountIn,
          min_out: quote.min_out ?? "0",
          fee: quote.fee ?? 3000,
          to: dest,
        },
        state.adminKey,
      );
      setPrepared(res as Record<string, unknown>);
      setDrawer({ open: true, title: "Convert+Withdraw Prepared", payload: res as unknown as JsonValue });
      setStatus("Prepared.");
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  async function doConvertExecute(reason: string) {
    if (!operator) {
      setStatus("Locked/Read-only: unlock to execute.");
      return;
    }
    if (!session.armed) {
      setStatus("Not ARMED.");
      return;
    }
    if (!quote?.ok) {
      setStatus("Quote first.");
      return;
    }
    setStatus("Executing…");
    try {
      const res = await convertWithdrawExecute(
        state.baseUrl,
        {
          token_in: tokenIn,
          token_out: stableOut,
          amount_in: amountIn,
          min_out: quote.min_out ?? "0",
          fee: quote.fee ?? 3000,
          to: dest,
          reason,
        },
        state.adminKey,
      );
      setDrawer({ open: true, title: "Convert+Withdraw Execute Result", payload: res as unknown as JsonValue });
      const summary = summarizeWithdrawExecution(res, "Convert+withdraw");
      if (summary.ok && saveRecipientOnConfirm) rememberRecipient(dest);
      setStatus(summary.detail);
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    } finally {
      setConfirmReason(false);
      setConfirmConvertExec(false);
    }
  }

  async function doWithdrawPrepare() {
    if (!operator) {
      setStatus("Locked/Read-only: unlock to prepare.");
      return;
    }
    if (!wToken || !wAmount.trim() || !isAddress(dest)) {
      setStatus("Missing token/amount/destination.");
      return;
    }
    setStatus("Preparing…");
    try {
      const res = await withdrawPrepare(state.baseUrl, { token: wToken, to: dest, amount: wAmount }, state.adminKey);
      setPrepared(res as Record<string, unknown>);
      setDrawer({ open: true, title: "Withdraw Prepared", payload: res as unknown as JsonValue });
      setStatus("Prepared.");
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  async function doWithdrawExecute(reason: string) {
    if (!operator) {
      setStatus("Locked/Read-only: unlock to execute.");
      return;
    }
    if (!session.armed) {
      setStatus("Not ARMED.");
      return;
    }
    setStatus("Executing…");
    try {
      const res = await withdrawExecute(state.baseUrl, { token: wToken, to: dest, amount: wAmount, reason }, state.adminKey);
      setDrawer({ open: true, title: "Withdraw Execute Result", payload: res as unknown as JsonValue });
      const summary = summarizeWithdrawExecution(res, "Withdraw");
      if (summary.ok && saveRecipientOnConfirm) rememberRecipient(dest);
      setStatus(summary.detail);
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    } finally {
      setConfirmReason(false);
      setConfirmWithdrawExec(false);
    }
  }

  const stableAddr = stableOut === "USDC" ? String(stables?.usdc ?? "") : String(stables?.usdt ?? "");
  const savedRecipients = (state.walletAddresses ?? []).filter((x) => isAddress(String(x || "")));
  const cashoutSteps = [
    { key: "destination", label: "Choose destination", done: isAddress(dest) },
    { key: "amount", label: "Choose amount", done: tab === "Convert" ? Boolean(amountIn.trim()) : Boolean(wAmount.trim()) },
    { key: "review", label: "Review", done: tab === "Convert" ? Boolean(quote?.ok) : Boolean(prepared) },
    { key: "confirm", label: "Confirm", done: false },
  ];

  function rememberRecipient(address: string) {
    const a = String(address || "").trim();
    if (!isAddress(a)) return;
    const walletAddresses = [a, ...(state.walletAddresses ?? []).map((x) => String(x || "").trim())]
      .filter((x, i, arr) => isAddress(x) && arr.indexOf(x) === i)
      .slice(0, 12);
    set({ walletAddresses, defaultWithdrawalDest: a });
  }

  async function refreshWipeState(options?: { silent?: boolean; source?: "manual" | "auto" }) {
    try {
      const wipe = await withdrawAllState(state.baseUrl, state.role === "operator" ? state.adminKey : undefined);
      setWipeState(wipe as Record<string, unknown>);
      setWipeLastRefreshAtMs(Date.now());
      setWipeRefreshError("");
      const wipeRecord = asRecord(wipe) ?? {};
      const approved = wipeRecord["approved_destination"];
      const pending = wipeRecord["pending_destination"];
      const candidate = typeof approved === "string" && approved ? approved : typeof pending === "string" ? pending : "";
      if (candidate) setWipeDestination((prev) => prev || candidate);
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e);
      if (options?.source === "auto" || options?.silent) {
        setWipeRefreshError(message);
      } else {
        setStatus(message);
      }
    }
  }

  async function saveWipeConfig(options: { enabled?: boolean; activate?: boolean; includeDestination?: boolean; statusLabel: string }) {
    if (!operator) {
      setStatus("Locked/Read-only: unlock to configure wipe control.");
      return;
    }
    const payload: Record<string, unknown> = {};
    if (typeof options.enabled === "boolean") payload.enabled = options.enabled;
    if (typeof options.activate === "boolean") payload.activate_destination = options.activate;
    if (options.includeDestination) {
      if (!isAddress(wipeDestination)) {
        setStatus("Enter a valid canonical destination first.");
        return;
      }
      payload.destination = wipeDestination;
    }
    try {
      const res = await withdrawAllConfig(state.baseUrl, payload, state.adminKey);
      setWipeState(res as Record<string, unknown>);
      setStatus(`${options.statusLabel} · ${String((res as any)?.reason_code ?? (res as any)?.last_reason_code ?? 'ok')}`);
      if (options.activate && options.includeDestination) rememberRecipient(wipeDestination);
      await refreshWipeState();
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  async function previewWipe() {
    if (!operator) {
      setStatus("Locked/Read-only: unlock to preview wipe flow.");
      return;
    }
    try {
      const res = await withdrawAllPreview(state.baseUrl, state.adminKey);
      setWipeState((prev) => ({ ...prev, last_preview_id: String((res as any)?.preview_id ?? ''), preview: res }));
      setDrawer({ open: true, title: "Withdraw Everything Preview", payload: res as unknown as JsonValue });
      setStatus((res as any)?.ok ? "Withdraw-everything preview ready." : `Preview blocked · ${String((res as any)?.reason_code ?? 'unknown')}`);
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  async function executeWipe() {
    if (!operator) {
      setStatus("Locked/Read-only: unlock to trigger wipe flow.");
      return;
    }
    const previewId = String(asRecord(wipeState)?.["last_preview_id"] ?? asRecord(asRecord(wipeState)?.["preview"])?.["preview_id"] ?? "");
    if (!previewId) {
      setStatus("Preview first to generate a fresh confirmation id.");
      return;
    }
    try {
      const res = await withdrawAllExecute(
        state.baseUrl,
        { preview_id: previewId, confirm_text: wipeConfirmationText, dry_run: withdrawMode !== "backend" },
        state.adminKey,
      );
      setDrawer({ open: true, title: "Withdraw Everything Result", payload: res as unknown as JsonValue });
      const summary = summarizeWithdrawAllExecution(res);
      setStatus(summary.detail);
      await refreshWipeState();
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  const wipeAutoRefreshActive = shouldAutoRefreshWithdrawAllState(wipeState);
  const wipeAutoRefreshDelayMs = nextWithdrawAllRefreshDelayMs(wipeState);

  useEffect(() => {
    if (!wipeAutoRefreshActive || !(wipeAutoRefreshDelayMs > 0)) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      if (cancelled) return;
      void refreshWipeState({ silent: true, source: "auto" });
    }, wipeAutoRefreshDelayMs);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [wipeAutoRefreshActive, wipeAutoRefreshDelayMs, wipeState, state.baseUrl, state.role, state.adminKey]);

  const wipeRecord = asRecord(wipeState) ?? {};
  const wipeCapital = asRecord(wipeRecord["capital_truth"]);
  const wipeCategories = asRecord(wipeCapital?.["categories"]);
  const wipeReason = String(wipeRecord["reason_code"] ?? "-");
  const wipeStatus = String(wipeRecord["status"] ?? "idle");
  const wipeWithdrawable = String(wipeRecord["withdrawable_balance_wei"] ?? wipeCategories?.["withdrawable_balance_wei"] ?? "0");
  const wipeApprovedDestination = String(wipeRecord["approved_destination"] ?? "");
  const wipePendingDestination = String(wipeRecord["pending_destination"] ?? "");
  const wipeDestinationStatus = String(wipeRecord["destination_status"] ?? "missing");
  const wipeActionAvailable = Boolean(wipeRecord["action_available"]);
  const wipeActionReason = String(wipeRecord["action_reason_code"] ?? wipeReason);
  const wipeConfirmationText = String(wipeRecord["execute_confirmation_text"] ?? "WITHDRAW EVERYTHING");
  const wipeExecutionSummary = summarizeWithdrawAllState(wipeState);
  const wipeResultSummary = asRecord(wipeRecord["last_result_summary"]);
  const wipeConfirmedCount = Number(wipeResultSummary?.["confirmed_item_count"] ?? 0) || 0;
  const wipeOutstandingCount = Number(wipeResultSummary?.["outstanding_item_count"] ?? 0) || 0;
  const wipeRevertedCount = Number(wipeResultSummary?.["reverted_item_count"] ?? 0) || 0;
  const wipeAttemptedCount = Number(wipeResultSummary?.["attempted_item_count"] ?? 0) || 0;
  const wipeRefreshDetail = describeWithdrawAllRefresh(wipeState, wipeLastRefreshAtMs);
  const wipeRefreshWarning = describeWithdrawAllRefreshWarning(wipeState);

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 40)}>
      <TopStatusBar title="Off-Ramp" subtitle="Convert to stable → withdraw with deterministic quoting" rightTag={rightTag} live={state.role === "operator"} />

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Destination</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Funds can only be withdrawn to allowlisted addresses (backend) and are enforced on-chain.
        </Text>
        <TextInput
          value={dest}
          onChangeText={setDest}
          placeholder="0x…"
          placeholderTextColor={theme.colors.textFaint}
          autoCapitalize="none"
          autoCorrect={false}
          style={{ marginTop: theme.spacing.md, padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, color: theme.colors.text, backgroundColor: theme.colors.surface1, fontFamily: "monospace" }}
        />
      </SurfaceCard>

      {savedRecipients.length ? (
        <>
          <View style={{ height: theme.spacing.md }} />
          <SurfaceCard glow="none">
            <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Saved recipients</Text>
            <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
              Tap a trusted destination to speed up repeat cash outs.
            </Text>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: theme.spacing.md }}>
              {savedRecipients.slice(0, 8).map((r) => (
                <Pressable
                  key={r}
                  onPress={() => setDest(r)}
                  style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: theme.radii.pill, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}
                >
                  <Text style={{ color: theme.colors.textMuted, ...theme.typography.mono }}>{r.slice(0, 8)}…{r.slice(-6)}</Text>
                </Pressable>
              ))}
            </View>
          </SurfaceCard>
        </>
      ) : null}

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="violet">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Withdraw Everything / Wipe Platform Capital</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Institutional control only. Requires an approved destination, an explicit enable toggle, a fresh preview id, and a deliberate confirmation. Backend blocks the flow when capital truth is degraded or withdrawable balance is unavailable.
        </Text>
        <Text style={{ color: theme.colors.textFaint, marginTop: theme.spacing.md, ...theme.typography.mono }}>
          status: {wipeStatus} · reason: {wipeReason}{"\n"}
          withdrawable: {wipeWithdrawable}{"\n"}
          approved: {String(wipeRecord["approved_destination"] ?? "(not set)")}{"\n"}
          last status: {String(wipeRecord["last_status"] ?? "idle")}
        </Text>
        {wipeExecutionSummary ? (
          <Text style={{ color: wipeExecutionSummary.ok ? theme.colors.textMuted : theme.colors.danger, marginTop: 8, ...theme.typography.body }}>
            {wipeExecutionSummary.headline} · {wipeExecutionSummary.detail}
          </Text>
        ) : null}
        {wipeAttemptedCount > 0 ? (
          <Text style={{ color: theme.colors.textFaint, marginTop: 8, ...theme.typography.mono }}>
            tracked items: {wipeAttemptedCount} · confirmed: {wipeConfirmedCount} · awaiting: {wipeOutstandingCount} · reverted: {wipeRevertedCount}
          </Text>
        ) : null}
        {wipeRefreshDetail ? (
          <Text style={{ color: theme.colors.textFaint, marginTop: 8, ...theme.typography.body }}>
            {wipeRefreshDetail}
          </Text>
        ) : null}
        {wipeRefreshWarning ? (
          <Text style={{ color: theme.colors.warn, marginTop: 8, ...theme.typography.body }}>
            Refresh degradation warning · {wipeRefreshWarning}
          </Text>
        ) : null}
        {wipeRefreshError ? (
          <Text style={{ color: theme.colors.danger, marginTop: 8, ...theme.typography.body }}>
            Auto-refresh warning · {wipeRefreshError}
          </Text>
        ) : null}
        <TextInput
          value={wipeDestination}
          onChangeText={setWipeDestination}
          placeholder="Canonical destination 0x…"
          placeholderTextColor={theme.colors.textFaint}
          autoCapitalize="none"
          autoCorrect={false}
          style={{ marginTop: theme.spacing.md, padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, color: theme.colors.text, backgroundColor: theme.colors.surface1, fontFamily: "monospace" }}
        />
        <View style={{ flexDirection: "row", gap: 10, flexWrap: "wrap", marginTop: theme.spacing.md }}>
          <Pressable onPress={() => void saveWipeConfig({ enabled: !Boolean(wipeRecord["enabled"]), statusLabel: Boolean(wipeRecord["enabled"]) ? "Wipe control disabled" : "Wipe control enabled" })} style={{ paddingVertical: 10, paddingHorizontal: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
            <Text style={{ color: theme.colors.text, fontWeight: "900" }}>{Boolean(wipeRecord["enabled"]) ? "Disable wipe control" : "Enable wipe control"}</Text>
          </Pressable>
          <Pressable onPress={() => void saveWipeConfig({ enabled: Boolean(wipeRecord["enabled"]), activate: false, includeDestination: true, statusLabel: "Destination staged" })} style={{ paddingVertical: 10, paddingHorizontal: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
            <Text style={{ color: theme.colors.text, fontWeight: "900" }}>Stage destination</Text>
          </Pressable>
          <Pressable onPress={() => void saveWipeConfig({ enabled: Boolean(wipeRecord["enabled"]), activate: true, includeDestination: true, statusLabel: "Destination approved" })} style={{ paddingVertical: 10, paddingHorizontal: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.violet }}>
            <Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>Approve destination</Text>
          </Pressable>
          <Pressable onPress={() => void previewWipe()} style={{ paddingVertical: 10, paddingHorizontal: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface2 }}>
            <Text style={{ color: theme.colors.text, fontWeight: "900" }}>Preview wipe</Text>
          </Pressable>
          <Pressable onPress={() => setConfirmWipeExec(true)} style={{ paddingVertical: 10, paddingHorizontal: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.violet, backgroundColor: theme.colors.surface1 }}>
            <Text style={{ color: theme.colors.text, fontWeight: "900" }}>Trigger withdraw everything</Text>
          </Pressable>
        </View>
        <Text style={{ color: theme.colors.textFaint, marginTop: theme.spacing.md, ...theme.typography.mono }}>
          Confirmation phrase: {wipeConfirmationText}
        </Text>
        {withdrawMode !== "backend" ? (
          <Text style={{ color: theme.colors.textFaint, marginTop: theme.spacing.md, ...theme.typography.mono }}>
            Mode is {withdrawMode}. Triggering the wipe flow prepares canonical tx data rather than broadcasting live transactions.
          </Text>
        ) : null}
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />
      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Cash Out Flow</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Guided steps keep the existing backend workflow intact while making off-ramp easier to operate.
        </Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: theme.spacing.md }}>
          {cashoutSteps.map((step, idx) => (
            <View key={step.key} style={{ minWidth: 120, paddingVertical: 10, paddingHorizontal: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: step.done ? theme.colors.cyan : theme.colors.border, backgroundColor: step.done ? theme.colors.surface2 : theme.colors.surface1 }}>
              <Text style={{ color: step.done ? theme.colors.text : theme.colors.textMuted, fontWeight: "900" }}>{idx + 1}. {step.label}</Text>
            </View>
          ))}
        </View>
        <View style={{ flexDirection: "row", gap: 10, marginTop: theme.spacing.md, flexWrap: "wrap" }}>
          <Pressable onPress={() => setSaveRecipientOnConfirm((v) => !v)} style={{ paddingVertical: 10, paddingHorizontal: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: saveRecipientOnConfirm ? theme.colors.cyan : theme.colors.border, backgroundColor: saveRecipientOnConfirm ? theme.colors.surface2 : theme.colors.surface1 }}>
            <Text style={{ color: saveRecipientOnConfirm ? theme.colors.text : theme.colors.textMuted, fontWeight: "900" }}>Save recipient {saveRecipientOnConfirm ? "ON" : "OFF"}</Text>
          </Pressable>
          <Pressable onPress={() => setConfirmEveryCashOut((v) => !v)} style={{ paddingVertical: 10, paddingHorizontal: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: confirmEveryCashOut ? theme.colors.cyan : theme.colors.border, backgroundColor: confirmEveryCashOut ? theme.colors.surface2 : theme.colors.surface1 }}>
            <Text style={{ color: confirmEveryCashOut ? theme.colors.text : theme.colors.textMuted, fontWeight: "900" }}>Confirm every cash out {confirmEveryCashOut ? "ON" : "OFF"}</Text>
          </Pressable>
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.md }} />
      <SegmentedTabs options={["Convert", "Withdraw"] as const} value={tab} onChange={setTab} />

      <View style={{ height: theme.spacing.md }} />
      {tab === "Convert" ? (
        <SurfaceCard glow="cyan">
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Convert → Withdraw</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
            Quotes use Uniswap V3 QuoterV2 deterministically. minOut is derived from slippage bps.
          </Text>

          <View style={{ marginTop: theme.spacing.md }}>
            <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Token In</Text>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
              {(tokens.length ? tokens : [tokenIn || "-"]).slice(0, 10).map((t) => {
                const active = t === tokenIn;
                return (
                  <Pressable
                    key={t}
                    onPress={() => setTokenIn(t)}
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
            <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Token Out</Text>
            <View style={{ flexDirection: "row", gap: 10, marginTop: 8 }}>
              {(["USDC", "USDT"] as const).map((s) => {
                const active = s === stableOut;
                return (
                  <Pressable
                    key={s}
                    onPress={() => {
                      setStableOut(s);
                      setQuote(null);
                    }}
                    style={{
                      paddingHorizontal: 12,
                      paddingVertical: 10,
                      borderRadius: theme.radii.pill,
                      borderWidth: 1,
                      borderColor: active ? theme.colors.cyan : theme.colors.border,
                      backgroundColor: active ? theme.colors.surface2 : theme.colors.surface1,
                    }}
                  >
                    <Text style={{ color: active ? theme.colors.text : theme.colors.textMuted, fontWeight: "900" }}>{s}</Text>
                  </Pressable>
                );
              })}
            </View>
            <Text style={{ color: theme.colors.textFaint, marginTop: 8, ...theme.typography.mono }}>Stable address: {stableAddr ? stableAddr : "(not configured)"}</Text>
          </View>

          <View style={{ marginTop: theme.spacing.md }}>
            <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Amount In (raw units)</Text>
            <TextInput
              value={amountIn}
              onChangeText={(v) => {
                setAmountIn(v);
                setQuote(null);
              }}
              placeholder="wei"
              placeholderTextColor={theme.colors.textFaint}
              keyboardType="numeric"
              style={{ marginTop: 8, padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, color: theme.colors.text, backgroundColor: theme.colors.surface1, fontFamily: "monospace" }}
            />
          </View>

          <View style={{ flexDirection: "row", gap: 10, marginTop: theme.spacing.md }}>
            <Pressable
              onPress={() => void doQuote()}
              style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface2, alignItems: "center" }}
            >
              <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>Quote</Text>
            </Pressable>
            <Pressable
              onPress={() => void doConvertPrepare()}
              style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.cyan, alignItems: "center" }}
            >
              <Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>Prepare</Text>
            </Pressable>
          </View>

          <View style={{ marginTop: 10 }}>
            <Pressable
              onPress={() => { if (confirmEveryCashOut) setConfirmConvertExec(true); else setConfirmReason(true); }}
              style={{ paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface1, borderWidth: 1, borderColor: theme.colors.border, alignItems: "center" }}
            >
              <Text style={{ color: theme.colors.text, fontWeight: "900" }}>Execute (backend mode only)</Text>
            </Pressable>
          </View>

          {quote?.ok ? (
            <View style={{ marginTop: theme.spacing.md }}>
              <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Quote</Text>
              <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
                expectedOut: <Text style={{ color: theme.colors.text, fontWeight: "900" }}>{quote.expected_out}</Text>
                {"\n"}
                minOut: <Text style={{ color: theme.colors.text, fontWeight: "900" }}>{quote.min_out}</Text>
                {"\n"}
                feeTier: <Text style={{ color: theme.colors.text, fontWeight: "900" }}>{quote.fee}</Text> · slippage {quote.slippage_bps} bps
              </Text>
            </View>
          ) : null}

          {withdrawMode !== "backend" ? (
            <Text style={{ color: theme.colors.textFaint, marginTop: theme.spacing.md, ...theme.typography.mono }}>
              Note: withdraw_mode is {withdrawMode}. Use Prepare and sign externally (WalletConnect). Execute requires backend mode.
            </Text>
          ) : null}
        </SurfaceCard>
      ) : (
        <SurfaceCard glow="violet">
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Withdraw (Direct)</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
            Preserves config → prepare → execute workflow. Use Convert tab to off-ramp into stable first.
          </Text>

          <View style={{ marginTop: theme.spacing.md }}>
            <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Token</Text>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
              {(tokens.length ? tokens : [wToken || "-"]).slice(0, 10).map((t) => {
                const active = t === wToken;
                return (
                  <Pressable
                    key={t}
                    onPress={() => setWToken(t)}
                    style={{
                      paddingHorizontal: 10,
                      paddingVertical: 8,
                      borderRadius: theme.radii.pill,
                      borderWidth: 1,
                      borderColor: active ? theme.colors.violet : theme.colors.border,
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
            <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Amount (raw units)</Text>
            <TextInput
              value={wAmount}
              onChangeText={setWAmount}
              placeholder="wei"
              placeholderTextColor={theme.colors.textFaint}
              keyboardType="numeric"
              style={{ marginTop: 8, padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, color: theme.colors.text, backgroundColor: theme.colors.surface1, fontFamily: "monospace" }}
            />
          </View>

          <View style={{ flexDirection: "row", gap: 10, marginTop: theme.spacing.md }}>
            <Pressable
              onPress={() => void doWithdrawPrepare()}
              style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.violet, alignItems: "center" }}
            >
              <Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>Prepare</Text>
            </Pressable>
            <Pressable
              onPress={() => { if (confirmEveryCashOut) setConfirmWithdrawExec(true); else setConfirmReason(true); }}
              style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface1, borderWidth: 1, borderColor: theme.colors.border, alignItems: "center" }}
            >
              <Text style={{ color: theme.colors.text, fontWeight: "900" }}>Execute</Text>
            </Pressable>
          </View>

          {withdrawMode !== "backend" ? (
            <Text style={{ color: theme.colors.textFaint, marginTop: theme.spacing.md, ...theme.typography.mono }}>
              Note: withdraw_mode is {withdrawMode}. Use Prepare and sign externally; Execute requires backend mode.
            </Text>
          ) : null}
        </SurfaceCard>
      )}

      {status ? <Text style={{ color: theme.colors.textFaint, marginTop: theme.spacing.md }}>{status}</Text> : null}

      <ReceiptDrawer visible={drawer.open} title={drawer.title} payload={drawer.payload} onClose={() => setDrawer({ open: false, title: "" })} />

      <ConfirmDialog
        visible={confirmConvertExec}
        title="Execute Convert+Withdraw"
        body="This will ask the backend to execute a live transaction only if withdraw_mode=backend. The result may be pending, sent, receipt unavailable, or confirmed rather than immediately completed. Requires ARMED session. A reason will be recorded in the audit log."
        confirmText="Continue"
        cancelText="Cancel"
        onCancel={() => setConfirmConvertExec(false)}
        onConfirm={() => {
          setConfirmConvertExec(false);
          setConfirmReason(true);
        }}
      />

      <ConfirmDialog
        visible={confirmWithdrawExec}
        title="Execute Withdraw"
        body="This will ask the backend to execute a live transaction only if withdraw_mode=backend. The result may be pending, sent, receipt unavailable, or confirmed rather than immediately completed. Requires ARMED session. A reason will be recorded in the audit log."
        confirmText="Continue"
        cancelText="Cancel"
        onCancel={() => setConfirmWithdrawExec(false)}
        onConfirm={() => {
          setConfirmWithdrawExec(false);
          setConfirmReason(true);
        }}
      />

      <ConfirmDialog
        visible={confirmWipeExec}
        title="Trigger Withdraw Everything"
        body="This uses a fresh preview id and the backend will only proceed if the canonical destination is approved, capital truth is healthy, and the flow is explicitly enabled. In txdata mode it prepares a wipe plan; in backend mode it can broadcast the prepared withdraw sequence. Submitted does not necessarily mean completed; item-level receipts may still be pending."
        confirmText="Trigger"
        cancelText="Cancel"
        onCancel={() => setConfirmWipeExec(false)}
        onConfirm={() => {
          setConfirmWipeExec(false);
          void executeWipe();
        }}
      />

      <ConfirmReasonDialog
        visible={confirmReason}
        title="Reason required"
        body="Provide a short reason for this action (stored in immutable audit log)."
        requireReason
        confirmText="Submit"
        cancelText="Cancel"
        onCancel={() => setConfirmReason(false)}
        onConfirm={(reason) => {
          // Determine which action was intended by current tab & context.
          if (tab === "Convert") void doConvertExecute(reason);
          else void doWithdrawExecute(reason);
        }}
      />
    </ScrollView>
  );
}
