import AsyncStorage from "@react-native-async-storage/async-storage";
import type { Opportunity, JsonValue } from "../utils/types";

export type TicketStage = "NEW" | "SIMULATED" | "PREFLIGHT" | "EXEC_SENT" | "MINED" | "DECODED" | "FAILED";

export type TicketTimeline = {
  selectedAt?: number;
  simulatedAt?: number;
  preflightAt?: number;
  sentAt?: number;
  minedAt?: number;
  decodedAt?: number;
  failedAt?: number;
};

export type TradeTicket = {
  id: string;
  createdAt: number;
  updatedAt: number;
  chain: string;
  oppId: string;
  strategy: string;
  routeId?: string;
  stage: TicketStage;
  timeline?: TicketTimeline;
  sendMode?: string;
  gasMode?: string;
  brainMode?: string;
  sizeMult?: number;
  borrowMult?: number;
  amountInOverride?: string;

  simulate?: JsonValue;
  trade?: JsonValue;
  receipt?: JsonValue;
  decoded?: JsonValue;
  pnl?: { realizedUsd?: number; profitRaw?: string; gasUsed?: string };
};

const STORAGE_KEY = "vax_ticket_history_v2";

function safeParseJson(s: string): unknown {
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}

export async function loadTickets(): Promise<TradeTicket[]> {
  const raw = await AsyncStorage.getItem(STORAGE_KEY);
  if (!raw) return [];
  const parsed = safeParseJson(raw);
  if (!Array.isArray(parsed)) return [];
  const out: TradeTicket[] = [];
  for (const it of parsed) {
    if (typeof it !== "object" || it === null) continue;
    const o = it as Record<string, unknown>;
    if (typeof o.id !== "string") continue;
    if (typeof o.oppId !== "string") continue;
    if (typeof o.chain !== "string") continue;
    if (typeof o.strategy !== "string") continue;
    const stage = String(o.stage || "NEW") as TicketStage;
    out.push({
      id: o.id,
      createdAt: Number(o.createdAt || Date.now()),
      updatedAt: Number(o.updatedAt || Date.now()),
      chain: o.chain,
      oppId: o.oppId,
      strategy: o.strategy,
      routeId: typeof o.routeId === "string" ? o.routeId : undefined,
      stage,
      timeline: typeof o.timeline === "object" && o.timeline !== null ? (o.timeline as TicketTimeline) : undefined,
      sendMode: typeof o.sendMode === "string" ? o.sendMode : undefined,
      gasMode: typeof o.gasMode === "string" ? o.gasMode : undefined,
      brainMode: typeof o.brainMode === "string" ? o.brainMode : undefined,
      sizeMult: typeof o.sizeMult === "number" ? o.sizeMult : undefined,
      borrowMult: typeof o.borrowMult === "number" ? o.borrowMult : undefined,
      amountInOverride: typeof o.amountInOverride === "string" ? o.amountInOverride : undefined,
      simulate: (o.simulate as JsonValue) ?? undefined,
      trade: (o.trade as JsonValue) ?? undefined,
      receipt: (o.receipt as JsonValue) ?? undefined,
      decoded: (o.decoded as JsonValue) ?? undefined,
      pnl: typeof o.pnl === "object" && o.pnl !== null ? (o.pnl as TradeTicket["pnl"]) : undefined,
    });
  }
  // newest first
  out.sort((a, b) => b.createdAt - a.createdAt);
  return out;
}

export async function saveTickets(tickets: readonly TradeTicket[], maxKeep: number = 120): Promise<void> {
  const pruned = [...tickets].sort((a, b) => b.createdAt - a.createdAt).slice(0, maxKeep);
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(pruned));
}

export function newTicket(opp: Opportunity, overrides?: { chain?: string; amountInOverride?: string; sendMode?: string; gasMode?: string; brainMode?: string }): TradeTicket {
  const ts = Date.now();
  const id = `t_${opp.id}_${ts}`;
  const rid = (opp.meta as Record<string, JsonValue> | undefined)?.["route_id"];
  return {
    id,
    createdAt: ts,
    updatedAt: ts,
    chain: String(overrides?.chain ?? opp.chain ?? ""),
    oppId: String(opp.id),
    strategy: String(opp.strategy),
    routeId: typeof rid === "string" ? rid : undefined,
    stage: "NEW",
    timeline: { selectedAt: ts },
    amountInOverride: overrides?.amountInOverride,
    sendMode: overrides?.sendMode,
    gasMode: overrides?.gasMode,
    brainMode: overrides?.brainMode,
  };
}

export function updateTicket(t: TradeTicket, patch: Partial<TradeTicket>): TradeTicket {
  const now = Date.now();
  const nextTimeline: TicketTimeline = { ...(t.timeline ?? { selectedAt: t.createdAt }) };

  const nextStage = patch.stage;
  if (nextStage && nextStage !== t.stage) {
    if (nextStage === "SIMULATED") nextTimeline.simulatedAt = now;
    if (nextStage === "PREFLIGHT") nextTimeline.preflightAt = now;
    if (nextStage === "EXEC_SENT") nextTimeline.sentAt = now;
    if (nextStage === "MINED") nextTimeline.minedAt = now;
    if (nextStage === "DECODED") nextTimeline.decodedAt = now;
    if (nextStage === "FAILED") nextTimeline.failedAt = now;
  }

  const mergedTimeline = patch.timeline ? { ...nextTimeline, ...patch.timeline } : nextTimeline;
  return { ...t, ...patch, timeline: mergedTimeline, updatedAt: now };
}
