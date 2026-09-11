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
export type WsMessage = SummaryMessage | DeltaMessage;

export type SummaryObservationHandler = (message: SummaryMessage, receivedAtMs: number) => void;
export type SummaryHandler = (message: WsMessage) => void;
export type ErrorHandler = (error: string) => void;

export type SummaryWebSocketOptions = {
  mode?: "summary" | "delta";
  fullEvery?: number;
  reconnectBaseMs?: number;
  reconnectMaxMs?: number;
  messageTimeoutMs?: number;
};

type WebSocketLike = WebSocket;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseMessage(raw: unknown): WsMessage | null {
  if (!isRecord(raw) || (raw.type !== "summary" && raw.type !== "delta") || !isRecord(raw.data)) {
    return null;
  }
  return raw as unknown as WsMessage;
}

export class VictorSummaryWS {
  private ws?: WebSocketLike;
  private alive = false;
  private reconnectTimer?: ReturnType<typeof setTimeout>;
  private timeoutTimer?: ReturnType<typeof setTimeout>;
  private handlers = new Set<SummaryHandler>();
  private observationHandlers = new Set<SummaryObservationHandler>();
  private errHandlers = new Set<ErrorHandler>();
  private backoff = 500;
  private baseUrl = "";
  private options: Required<SummaryWebSocketOptions> = {
    mode: "delta",
    fullEvery: 10,
    reconnectBaseMs: 500,
    reconnectMaxMs: 8_000,
    messageTimeoutMs: 15_000,
  };
  private lastMessageAtMs = 0;

  onMessage(handler: SummaryHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  /** Backward-compatible alias for existing screens; transport remains centralized here. */
  on(handler: SummaryHandler): () => void {
    return this.onMessage(handler);
  }

  /** Reconciliation-facing callback. Only complete summary messages are exposed. */
  onObservation(handler: SummaryObservationHandler): () => void {
    this.observationHandlers.add(handler);
    return () => this.observationHandlers.delete(handler);
  }

  onError(handler: ErrorHandler): () => void {
    this.errHandlers.add(handler);
    return () => this.errHandlers.delete(handler);
  }

  connect(baseUrl: string, options?: SummaryWebSocketOptions): void {
    this.disconnect();
    this.alive = true;
    this.baseUrl = baseUrl;
    this.options = {
      ...this.options,
      ...options,
      reconnectBaseMs: Math.max(100, options?.reconnectBaseMs ?? this.options.reconnectBaseMs),
      reconnectMaxMs: Math.max(100, options?.reconnectMaxMs ?? this.options.reconnectMaxMs),
      messageTimeoutMs: Math.max(1_000, options?.messageTimeoutMs ?? this.options.messageTimeoutMs),
    };
    this.backoff = this.options.reconnectBaseMs;
    this.openSocket();
  }

  /** Backward-compatible alias for existing screens. */
  open(baseUrl: string, options?: SummaryWebSocketOptions): void {
    this.connect(baseUrl, options);
  }

  disconnect(): void {
    this.alive = false;
    this.clearTimers();
    const ws = this.ws;
    this.ws = undefined;
    try {
      ws?.close();
    } catch {
      // Transport teardown is best-effort.
    }
  }

  /** Backward-compatible alias for existing screens. */
  close(): void {
    this.disconnect();
  }

  private clearTimers(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.timeoutTimer) clearTimeout(this.timeoutTimer);
    this.reconnectTimer = undefined;
    this.timeoutTimer = undefined;
  }

  private emitError(error: string): void {
    for (const handler of this.errHandlers) handler(error);
  }

  private scheduleReconnect(): void {
    if (!this.alive || this.reconnectTimer) return;
    const wait = this.backoff;
    this.backoff = Math.min(this.options.reconnectMaxMs, this.backoff * 1.6);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = undefined;
      this.openSocket();
    }, wait);
  }

  private armMessageTimeout(): void {
    if (this.timeoutTimer) clearTimeout(this.timeoutTimer);
    if (!this.alive) return;
    this.timeoutTimer = setTimeout(() => {
      this.timeoutTimer = undefined;
      if (!this.alive || !this.ws || Date.now() - this.lastMessageAtMs < this.options.messageTimeoutMs) {
        if (this.alive) this.armMessageTimeout();
        return;
      }
      this.emitError("ws_timeout");
      try {
        this.ws.close();
      } catch {
        this.scheduleReconnect();
      }
    }, this.options.messageTimeoutMs);
  }

  private openSocket(): void {
    if (!this.alive) return;
    const mode = this.options.mode;
    const fullEvery = this.options.fullEvery;
    const qs = `?mode=${encodeURIComponent(mode)}&full_every=${encodeURIComponent(String(fullEvery))}`;
    const wsUrl = buildWsUrl(this.baseUrl, `/ws/summary${qs}`);

    try {
      const ws = new WebSocket(wsUrl);
      this.ws = ws;
      ws.onopen = () => {
        this.backoff = this.options.reconnectBaseMs;
        this.lastMessageAtMs = Date.now();
        this.armMessageTimeout();
      };
      ws.onmessage = (event) => {
        const receivedAtMs = Date.now();
        this.lastMessageAtMs = receivedAtMs;
        this.armMessageTimeout();
        try {
          const parsed: unknown = JSON.parse(String(event.data));
          const message = parseMessage(parsed);
          if (!message) {
            this.emitError("ws_invalid_message");
            return;
          }
          for (const handler of this.handlers) handler(message);
          if (message.type === "summary") {
            for (const handler of this.observationHandlers) handler(message, receivedAtMs);
          }
        } catch (error: unknown) {
          this.emitError(error instanceof Error ? error.message : String(error));
        }
      };
      ws.onerror = () => this.emitError("ws_error");
      ws.onclose = () => {
        if (!this.alive) return;
        this.ws = undefined;
        this.clearTimers();
        this.scheduleReconnect();
      };
    } catch (error: unknown) {
      this.emitError(error instanceof Error ? error.message : String(error));
      this.scheduleReconnect();
    }
  }
}
