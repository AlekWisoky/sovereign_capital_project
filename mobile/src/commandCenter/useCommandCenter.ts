import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { CommandCenterSnapshot, ControlPatch, ExplainResponse } from "./types";
import { createBackendCommandCenterProvider, createMockCommandCenterProvider } from "./provider";
import { useStore } from "../state/store";

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

function useCommandCenterController(): CommandCenterValue {
  const { state } = useStore();
  const [source, setSource] = useState<DataSource>((state as any).ccDataSource ?? "mock");
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
    const ms = Number((state as any).ccRefreshMs ?? 4500);
    timer.current = setInterval(() => void refresh(), Math.max(1500, ms));
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider]);

  async function setControls(patch: ControlPatch, reason: string) {
    const result = await provider.setControls(patch, reason);
    return result;
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

export function CommandCenterProvider({ children }: { children: React.ReactNode }) {
  const value = useCommandCenterController();
  return React.createElement(CommandCenterContext.Provider, { value }, children);
}

export function useCommandCenter() {
  const value = useContext(CommandCenterContext);
  if (!value) throw new Error("CommandCenterProvider missing");
  return value;
}
