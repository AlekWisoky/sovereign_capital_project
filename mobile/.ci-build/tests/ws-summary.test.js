"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const wsSummary_1 = require("../src/api/wsSummary");
class FakeWebSocket {
    constructor(url) {
        this.closed = false;
        this.url = url;
        FakeWebSocket.instances.push(this);
    }
    close() {
        this.closed = true;
        this.onclose?.();
    }
    emitOpen() {
        this.onopen?.();
    }
    emitMessage(data) {
        this.onmessage?.({ data: JSON.stringify(data) });
    }
}
FakeWebSocket.instances = [];
function installFakeWebSocket() {
    FakeWebSocket.instances = [];
    const target = globalThis;
    const previous = target.WebSocket;
    target.WebSocket = FakeWebSocket;
    return () => {
        target.WebSocket = previous;
        FakeWebSocket.instances = [];
    };
}
(0, node_test_1.default)('summary adapter connects only to the backend /ws/summary route', () => {
    const restore = installFakeWebSocket();
    try {
        const ws = new wsSummary_1.VictorSummaryWS();
        ws.connect('https://api.example.test', { mode: 'summary' });
        strict_1.default.equal(FakeWebSocket.instances.length, 1);
        strict_1.default.equal(FakeWebSocket.instances[0].url, 'wss://api.example.test/ws/summary?mode=summary&full_every=10');
        ws.disconnect();
    }
    finally {
        restore();
    }
});
(0, node_test_1.default)('complete summary messages are exposed to the reconciliation-facing observation callback', () => {
    const restore = installFakeWebSocket();
    try {
        const ws = new wsSummary_1.VictorSummaryWS();
        const observed = [];
        ws.onObservation((message, receivedAtMs) => observed.push({ message, receivedAtMs }));
        ws.connect('https://api.example.test', { mode: 'summary' });
        const message = {
            type: 'summary',
            data: { chain: 'base', block: 123, opp_count: 4 },
        };
        FakeWebSocket.instances[0].emitOpen();
        FakeWebSocket.instances[0].emitMessage(message);
        strict_1.default.equal(observed.length, 1);
        strict_1.default.deepEqual(observed[0].message, message);
        strict_1.default.equal(Number.isFinite(observed[0].receivedAtMs), true);
        ws.disconnect();
    }
    finally {
        restore();
    }
});
(0, node_test_1.default)('malformed websocket payloads are rejected and never reach reconciliation', () => {
    const restore = installFakeWebSocket();
    try {
        const ws = new wsSummary_1.VictorSummaryWS();
        const observed = [];
        const errors = [];
        ws.onObservation((message) => observed.push(message));
        ws.onError((error) => errors.push(error));
        ws.connect('https://api.example.test', { mode: 'summary' });
        FakeWebSocket.instances[0].emitMessage({ type: 'summary', data: null });
        FakeWebSocket.instances[0].emitMessage({ type: 'unknown', data: {} });
        strict_1.default.equal(observed.length, 0);
        strict_1.default.equal(errors.length, 2);
        strict_1.default.deepEqual(errors, ['ws_invalid_message', 'ws_invalid_message']);
        ws.disconnect();
    }
    finally {
        restore();
    }
});
(0, node_test_1.default)('disconnect is terminal for the current adapter lifecycle', () => {
    const restore = installFakeWebSocket();
    try {
        const ws = new wsSummary_1.VictorSummaryWS();
        ws.connect('https://api.example.test', { mode: 'summary' });
        const socket = FakeWebSocket.instances[0];
        ws.disconnect();
        strict_1.default.equal(socket.closed, true);
        socket.onclose?.();
        strict_1.default.equal(FakeWebSocket.instances.length, 1);
    }
    finally {
        restore();
    }
});
