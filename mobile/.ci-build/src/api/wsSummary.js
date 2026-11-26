"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.VictorSummaryWS = void 0;
const url_1 = require("./url");
function isRecord(value) {
    return typeof value === "object" && value !== null;
}
function parseMessage(raw) {
    if (!isRecord(raw) || (raw.type !== "summary" && raw.type !== "delta") || !isRecord(raw.data)) {
        return null;
    }
    return raw;
}
class VictorSummaryWS {
    constructor() {
        this.alive = false;
        this.handlers = new Set();
        this.observationHandlers = new Set();
        this.errHandlers = new Set();
        this.backoff = 500;
        this.baseUrl = "";
        this.options = {
            mode: "delta",
            fullEvery: 10,
            reconnectBaseMs: 500,
            reconnectMaxMs: 8000,
            messageTimeoutMs: 15000,
        };
        this.lastMessageAtMs = 0;
    }
    onMessage(handler) {
        this.handlers.add(handler);
        return () => this.handlers.delete(handler);
    }
    /** Backward-compatible alias for existing screens; transport remains centralized here. */
    on(handler) {
        return this.onMessage(handler);
    }
    /** Reconciliation-facing callback. Only complete summary messages are exposed. */
    onObservation(handler) {
        this.observationHandlers.add(handler);
        return () => this.observationHandlers.delete(handler);
    }
    onError(handler) {
        this.errHandlers.add(handler);
        return () => this.errHandlers.delete(handler);
    }
    connect(baseUrl, options) {
        this.disconnect();
        this.alive = true;
        this.baseUrl = baseUrl;
        this.options = {
            ...this.options,
            ...options,
            reconnectBaseMs: Math.max(100, options?.reconnectBaseMs ?? this.options.reconnectBaseMs),
            reconnectMaxMs: Math.max(100, options?.reconnectMaxMs ?? this.options.reconnectMaxMs),
            messageTimeoutMs: Math.max(1000, options?.messageTimeoutMs ?? this.options.messageTimeoutMs),
        };
        this.backoff = this.options.reconnectBaseMs;
        this.openSocket();
    }
    /** Backward-compatible alias for existing screens. */
    open(baseUrl, options) {
        this.connect(baseUrl, options);
    }
    disconnect() {
        this.alive = false;
        this.clearTimers();
        const ws = this.ws;
        this.ws = undefined;
        try {
            ws?.close();
        }
        catch {
            // Transport teardown is best-effort.
        }
    }
    /** Backward-compatible alias for existing screens. */
    close() {
        this.disconnect();
    }
    clearTimers() {
        if (this.reconnectTimer)
            clearTimeout(this.reconnectTimer);
        if (this.timeoutTimer)
            clearTimeout(this.timeoutTimer);
        this.reconnectTimer = undefined;
        this.timeoutTimer = undefined;
    }
    emitError(error) {
        for (const handler of this.errHandlers)
            handler(error);
    }
    scheduleReconnect() {
        if (!this.alive || this.reconnectTimer)
            return;
        const wait = this.backoff;
        this.backoff = Math.min(this.options.reconnectMaxMs, this.backoff * 1.6);
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = undefined;
            this.openSocket();
        }, wait);
    }
    armMessageTimeout() {
        if (this.timeoutTimer)
            clearTimeout(this.timeoutTimer);
        if (!this.alive)
            return;
        this.timeoutTimer = setTimeout(() => {
            this.timeoutTimer = undefined;
            if (!this.alive || !this.ws || Date.now() - this.lastMessageAtMs < this.options.messageTimeoutMs) {
                if (this.alive)
                    this.armMessageTimeout();
                return;
            }
            this.emitError("ws_timeout");
            try {
                this.ws.close();
            }
            catch {
                this.scheduleReconnect();
            }
        }, this.options.messageTimeoutMs);
    }
    openSocket() {
        if (!this.alive)
            return;
        const mode = this.options.mode;
        const fullEvery = this.options.fullEvery;
        const qs = `?mode=${encodeURIComponent(mode)}&full_every=${encodeURIComponent(String(fullEvery))}`;
        const wsUrl = (0, url_1.buildWsUrl)(this.baseUrl, `/ws/summary${qs}`);
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
                    const parsed = JSON.parse(String(event.data));
                    const message = parseMessage(parsed);
                    if (!message) {
                        this.emitError("ws_invalid_message");
                        return;
                    }
                    for (const handler of this.handlers)
                        handler(message);
                    if (message.type === "summary") {
                        for (const handler of this.observationHandlers)
                            handler(message, receivedAtMs);
                    }
                }
                catch (error) {
                    this.emitError(error instanceof Error ? error.message : String(error));
                }
            };
            ws.onerror = () => this.emitError("ws_error");
            ws.onclose = () => {
                if (!this.alive)
                    return;
                this.ws = undefined;
                this.clearTimers();
                this.scheduleReconnect();
            };
        }
        catch (error) {
            this.emitError(error instanceof Error ? error.message : String(error));
            this.scheduleReconnect();
        }
    }
}
exports.VictorSummaryWS = VictorSummaryWS;
