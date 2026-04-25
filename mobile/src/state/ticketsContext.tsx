import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { loadTickets, saveTickets, type TradeTicket, updateTicket as patchTicket } from "./tickets";

const Ctx = createContext<{
  tickets: TradeTicket[];
  refresh: () => Promise<void>;
  upsert: (t: TradeTicket) => Promise<void>;
  patch: (id: string, patch: Partial<TradeTicket>) => Promise<void>;
  clear: () => Promise<void>;
} | null>(null);

export function TicketsProvider(props: { children: React.ReactNode }) {
  const [tickets, setTickets] = useState<TradeTicket[]>([]);

  async function refresh() {
    const t = await loadTickets();
    setTickets(t);
  }

  async function persist(next: TradeTicket[]) {
    setTickets(next);
    await saveTickets(next);
  }

  async function upsert(t: TradeTicket) {
    const next = [t, ...tickets.filter((x) => x.id !== t.id)];
    await persist(next);
  }

  async function patch(id: string, p: Partial<TradeTicket>) {
    const cur = tickets.find((x) => x.id === id);
    if (!cur) return;
    const nextTicket = patchTicket(cur, p);
    await upsert(nextTicket);
  }

  async function clear() {
    await persist([]);
  }

  useEffect(() => {
    void refresh();
  }, []);

  const api = useMemo(() => ({ tickets, refresh, upsert, patch, clear }), [tickets]);
  return <Ctx.Provider value={api}>{props.children}</Ctx.Provider>;
}

export function useTickets() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useTickets must be used within TicketsProvider");
  return v;
}
