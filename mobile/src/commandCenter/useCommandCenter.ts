import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Alert } from "react-native";
import type { CommandCenterSnapshot, ControlPatch, ExplainResponse } from "./types";
import { createBackendCommandCenterProvider, createMockCommandCenterProvider } from "./provider";
import { useStore } from "../state/store";
import { guardMutation, mutationKindForSettingsPatch } from "../api/mutationGuard";
import {
  Reconciler,
  type ReconciliationState,
} from "../api/reconciliation";

export type DataSource = "backend" | "mock";

type CommandCenterValue = {
  snapshot: CommandCenterSnapshot | null;
  reconciliation: ReconciliationState<CommandCenterSnapshot>;
  loading: boolean;
  error: string;
  refresh: () => Promise<void>;
  source: DataSource;
  setSource: (source: DataSource) => void;
  setControls: (patch: ControlPatch, reason: string) => Promise<{ ok: boolean; error?: string }>;
  explain: () => Promise<ExplainResponse>;
  auditTail: (limit: number) => Promise<{ ok: boolean; items: unknown[] }>;
};

const CommandCenterContext = createContext<CommandCenterValue | null>(null);

function confirmMutation(title: string, message: string): Promise<boolean> {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value: boolean) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };
    Alert.alert(
      title,
      message,
      [
        { text: "Cancel", style: "cancel", onPress: () => finish(false) },
        { text: "Confirm", style: "destructive", onPress: () => finish(true) },
      ],
      { cancelable: true, onDismiss: () => finish(false) },
    );
  });
}

function useCommandCenterController(): CommandCenterValue {
  const { state, session } = useStore();
  const [source, setSource] = useState<DataSource>(state.ccDataSource ?? "backend");
  const [snapshot, setSnapshot] = useState<CommandCenterSnapshot | null>(null);
  const [reconciliation, setReconciliation] = useState<ReconciliationState<CommandCenterSnapshot>>(
    () => new Reconciler<CommandCenterSnapshot>().snapshot(),
  );
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconcilerRef = useRef<Reconciler<CommandCenterSnapshot> | null>(null);

  const provider = useMemo(() => {
    if (source === "backend") return createBackendCommandCenterProvider(state.baseUrl, state.role === "operator" ? state.adminKey : undefined);
    return createMockCommandCenterProvider();
  }, [source, state.baseUrl, state.adminKey, state.role]);

  function getReconciler(): Reconciler<CommandCenterSnapshot> {
    if (!reconcilerRef.current) reconcilerRef.current = new Reconciler<CommandCenterSnapshot>();
    return reconcilerRef.current;
  }

  async function refresh() {
    setLoading(true);
    const reconciler = getReconciler();
    try {
      const snap = await provider.snapshot();
      // Polling/provider reads are authoritative. The portfolio timestamp is the
      // canonical observation timestamp when the backend supplies one.
      reconciler.acceptAuthoritative(snap, snap.portfolio.updatedAtMs, Date.now());
      const next = reconciler.snapshot();
      setSnapshot(next.value ?? null);
      setReconciliation(next);
      setError("");
    } catch (e: unknown) {
      reconciler.recordError(e);
      const next = reconciler.snapshot();
      setReconciliation(next);
      setSnapshot(next.value ?? null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // A source/base-url change starts a new reconciliation epoch; observations
    // from the previous provider must not become truth for the new provider.
    reconcilerRef.current = new Reconciler<CommandCenterSnapshot>();
    setReconciliation(reconcilerRef.current.snapshot());
    setSnapshot(null);
    void refresh();
    if (timer.current) clearInterval(timer.current);
    const ms = Number(state.ccRefreshMs ?? 4500);
    timer.current = setInterval(() => void refresh(), Math.max(1500, ms));
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider]);

  async function setControls(patch: ControlPatch, reason: string) {
    const context = {
      role: state.role === "operator" ? "operator" as const : "read_only" as const,
      locked: Boolean(session.locked),
      adminKeyPresent: Boolean(state.adminKey?.trim()),
      backendReachable: source === "backend" && snapshot !== null && !error,
      // Live authority remains closed until the explicit Issue #89 activation review.
      backendLiveAuthority: false,
      explicitConfirmation: false,
    };
    const kind = mutationKindForSettingsPatch(patch as Record<string, unknown>);
    const preflight = guardMutation(kind, context);
    if (!preflight.allowed && preflight.reasonCode !== "explicit_confirmation_required") {
      return { ok: false, error: `mutation_denied:${preflight.reasonCode}` };
    }

    const confirmed = await confirmMutation(
      "Confirm operator change",
      `${reason}\n\nThis changes backend operator state. Confirm only if this action is intentional.`,
    );
    if (!confirmed) return { ok: false, error: "mutation_cancelled" };

    const allowed = guardMutation(kind, { ...context, explicitConfirmation: true });
    if (!allowed.allowed) return { ok: false, error: `mutation_denied:${allowed.reasonCode}` };
    return await provider.setControls(patch, reason);
  }

  async function explain(): Promise<ExplainResponse> {
    return await provider.explain();
  }

  async function auditTail(limit: number) {
    return await provider.auditTail(limit);
  }

  return {
    snapshot,
    reconciliation,
    loading,
    error,
    refresh,
    source,
    setSource,
    setControls,
    explain,
    auditTail,
  };
}

export function CommandCenterProvider({ children }: { children: React.ReactNode }) {
  const value = useCommandCenterController();
  return React.createElement(CommandCenterContext.Provider, { value }, children);
}

export function useCommandCenter() {
  const value = useContext(CommandCenterContext);
  if (!value) throw new Error("CommandCenterProvider missing");
  return value;
}
