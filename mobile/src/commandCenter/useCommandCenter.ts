import React, { Alert, createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { CommandCenterSnapshot, ControlPatch, ExplainResponse } from "./types";
import { createBackendCommandCenterProvider, createMockCommandCenterProvider } from "./provider";
import { useStore } from "../state/store";
import { guardMutation, mutationKindForSettingsPatch } from "../api/mutationGuard";

export type DataSource = "backend" | "mock";

type CommandCenterValue = {
  snapshot: CommandCenterSnapshot | null;
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
    Alert.alert(title, message, [
      { text: "Cancel", style: "cancel", onPress: () => resolve(false) },
      { text: "Confirm", style: "destructive", onPress: () => resolve(true) },
    ], { cancelable: true, onDismiss: () => resolve(false) });
  });
}

function useCommandCenterController(): CommandCenterValue {
  const { state } = useStore();
  const [source, setSource] = useState<DataSource>(state.ccDataSource ?? "backend");
  const [snapshot, setSnapshot] = useState<CommandCenterSnapshot | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const provider = useMemo(() => {
    if (source === "backend") return createBackendCommandCenterProvider(state.baseUrl, state.role === "operator" ? state.adminKey : undefined);
    return createMockCommandCenterProvider();
  }, [source, state.baseUrl, state.adminKey, state.role]);

  async function refresh() {
    setLoading(true);
    try {
      const snap = await provider.snapshot();
      setSnapshot(snap);
      setError("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
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
      locked: sessionLocked(state),
      adminKeyPresent: Boolean(state.adminKey?.trim()),
      backendReachable: source === "backend" && snapshot !== null && !error,
      // Live authority is deliberately false until the backend reports an
      // explicit activation state. Issue #89 is the activation gate.
      backendLiveAuthority: false,
      explicitConfirmation: false,
    };
    const kind = mutationKindForSettingsPatch(patch as Record<string, unknown>);
    const preflight = guardMutation(kind, context);
    if (!preflight.allowed && preflight.reasonCode !== "explicit_confirmation_required") {
      return { ok: false, error: `mutation_denied:${preflight.reasonCode}` };
    }

    const confirmed = await confirmMutation("Confirm operator change", `${reason}\n\nThis changes backend operator state. Confirm only if this action is intentional.`);
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

function sessionLocked(state: ReturnType<typeof useStore>["state"]): boolean {
  return Boolean(state.role !== "operator" || false);
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
