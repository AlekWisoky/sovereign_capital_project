import { buildWsUrl } from "./url";
import { RuntimeState } from "../utils/types";

type Handler = (st: RuntimeState) => void;
type ErrorHandler = (err: string) => void;

export class VictorWS {
  private ws?: WebSocket;
  private alive = false;
  private handlers: Handler[] = [];
  private errHandlers: ErrorHandler[] = [];
  private backoff = 500;

  onState(h: Handler) { this.handlers.push(h); }
  onError(h: ErrorHandler) { this.errHandlers.push(h); }

  connect(baseUrl: string, opts?: { multichain?: boolean; chainFilter?: () => string }) {
    this.alive = true;
    this.backoff = 500;
    this.open(baseUrl, opts);
  }

  disconnect() {
    this.alive = false;
    try { this.ws?.close(); } catch {}
    this.ws = undefined;
  }

  private open(baseUrl: string, opts?: { multichain?: boolean; chainFilter?: () => string }) {
    if (!this.alive) return;
    const path = opts?.multichain ? "/ws/multichain" : "/ws";
    const wsUrl = buildWsUrl(baseUrl, path);
    try {
      const ws = new WebSocket(wsUrl);
      this.ws = ws;

      ws.onopen = () => { this.backoff = 500; };
      ws.onmessage = (ev) => {
        try {
          const parsed: unknown = JSON.parse(String(ev.data));
          const msg = (typeof parsed === "object" && parsed !== null ? (parsed as Record<string, unknown>) : null);
          if (msg && msg["type"] === "state" && msg["data"]) {
            if (opts?.multichain) {
              const want = (opts.chainFilter ? opts.chainFilter() : "") || "";
              const got = String(msg["chain"] ?? "");
              if (want && got && want !== got) return;
            }
            const st = msg["data"] as RuntimeState;
            for (const h of this.handlers) h(st);
          }
        } catch (e: unknown) {
          const emsg = e instanceof Error ? e.message : String(e);
          for (const h of this.errHandlers) h(emsg);
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
