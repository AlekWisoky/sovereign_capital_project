import { buildWsUrl } from "./url";
import type { JsonValue } from "../utils/types";
import type { ProjectionCompatibility, SummaryReadContract } from "../commandCenter/types";

export type SummaryData = {
  summaryContract?: SummaryReadContract;
  projectionCompatibility?: ProjectionCompatibility;
  chain?: string;
  block?: number;
  scan_ms?: number;
  opp_count?: number;
  metrics?: {
    attempted?: number;
    succeeded?: number;
    failed?: number;
    flashLoans?: number;
    realized_profit_raw?: string;
    efficiency_pct?: number;
    success_rate_pct?: number;
    gas_mode?: string;
    send_mode?: string;
  };
  execution_gate?: {
    blocked?: boolean;
    reason_code?: string;
    reason_codes?: string[];
    suggested_next_action?: string;
  };
  hold?: {
    blocked?: boolean;
    reason_code?: string;
    reason_codes?: string[];
    suggested_next_action?: string;
  };
  execution_advisory?: {
    active?: boolean;
    class?: string;
    reason_code?: string;
    next_action?: string;
  };
  auto_trade_gate?: {
    allowed?: boolean;
    stage?: string;
    reason_code?: string;
    reason_codes?: string[];
    next_action?: string;
  };
  auto_trade_recovery?: {
    blocked?: boolean;
    ready?: boolean;
    status?: string;
    stage?: string;
    reason_code?: string;
    reason_codes?: string[];
    next_action?: string;
    component?: string;
    history_status?: string;
    history_component?: string;
    history_stage?: string;
    degraded_count?: number;
    degradation_severity_class?: string;
    reliability_class?: string;
  };
  top_opportunity?: {
    id?: string;
    strategy?: string;
    expected_profit_raw?: string;
    can_execute?: boolean;
    route_id?: string;
    profit_after_gas_estimate_wei?: string;
    expected_profit_after_costs_wei?: string;
    can_execute_after_costs?: boolean;
    execution_allowed?: boolean;
    execution_gate_reason_code?: string;
    hold_reason_code?: string;
    auto_trade_allowed?: boolean;
    auto_trade_gate_stage?: string;
    auto_trade_gate_reason_code?: string;
    auto_trade_gate_reason_codes?: string[];
    auto_trade_gate_next_action?: string;
    auto_trade_recovery_status?: string;
    auto_trade_recovery_reason_code?: string;
    auto_trade_recovery_reason_codes?: string[];
    auto_trade_recovery_next_action?: string;
    auto_trade_recovery_ready?: boolean;
    auto_trade_recovery_component?: string;
    auto_trade_recovery_history_status?: string;
    auto_trade_recovery_history_component?: string;
    auto_trade_recovery_history_stage?: string;
    auto_trade_recovery_degraded_count?: number;
    auto_trade_recovery_degradation_severity_class?: string;
    auto_trade_recovery_reliability_class?: string;
    meta?: Record<string, JsonValue>;
  } | null;
};

export type SummaryMessage = { type: "summary"; data: SummaryData };
export type DeltaMessage = { type: "delta"; data: Partial<SummaryData> };
export type WsMessage = SummaryMessage | DeltaMessage | { type: string; data: JsonValue };

type SummaryHandler = (msg: WsMessage) => void;
type ErrorHandler = (err: string) => void;

export class VictorSummaryWS {
  private ws?: WebSocket;
  private alive = false;
  private handlers: SummaryHandler[] = [];
  private errHandlers: ErrorHandler[] = [];
  private backoff = 500;

  onMessage(h: SummaryHandler) { this.handlers.push(h); }
  onError(h: ErrorHandler) { this.errHandlers.push(h); }

  connect(baseUrl: string, opts?: { mode?: "summary" | "delta"; fullEvery?: number }) {
    this.alive = true;
    this.backoff = 500;
    this.open(baseUrl, opts);
  }

  disconnect() {
    this.alive = false;
    try { this.ws?.close(); } catch {}
    this.ws = undefined;
  }

  private open(baseUrl: string, opts?: { mode?: "summary" | "delta"; fullEvery?: number }) {
    if (!this.alive) return;
    const mode = opts?.mode ?? "delta";
    const fullEvery = Number(opts?.fullEvery ?? 10);
    const qs = `?mode=${encodeURIComponent(mode)}&full_every=${encodeURIComponent(String(fullEvery))}`;
    const wsUrl = buildWsUrl(baseUrl, "/ws/summary" + qs);

    try {
      const ws = new WebSocket(wsUrl);
      this.ws = ws;

      ws.onopen = () => { this.backoff = 500; };
      ws.onmessage = (ev) => {
        try {
          const parsed: unknown = JSON.parse(String(ev.data));
          // best-effort typing (backend message is already JSON-safe)
          for (const h of this.handlers) h(parsed as WsMessage);
        } catch (e: unknown) {
          const msg = e instanceof Error ? e.message : String(e);
          for (const h of this.errHandlers) h(msg);
        }
      };
      ws.onerror = () => {
        for (const h of this.errHandlers) h("ws_error");
      };
      ws.onclose = () => {
        if (!this.alive) return;
        const wait = this.backoff;
        this.backoff = Math.min(8000, this.backoff * 1.6);
        setTimeout(() => this.open(baseUrl, opts), wait);
      };
    } catch {
      const wait = this.backoff;
      this.backoff = Math.min(8000, this.backoff * 1.6);
      setTimeout(() => this.open(baseUrl, opts), wait);
    }
  }
}
