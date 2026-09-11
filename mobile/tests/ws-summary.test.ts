import assert from 'node:assert/strict';
import test from 'node:test';
import { VictorSummaryWS, type SummaryMessage } from '../src/api/wsSummary';

type FakeSocket = {
  url: string;
  onopen?: () => void;
  onmessage?: (event: { data: string }) => void;
  onerror?: () => void;
  onclose?: () => void;
  close: () => void;
};

class FakeWebSocket implements FakeSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  onopen?: () => void;
  onmessage?: (event: { data: string }) => void;
  onerror?: () => void;
  onclose?: () => void;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  close(): void {
    this.closed = true;
    this.onclose?.();
  }

  emitOpen(): void {
    this.onopen?.();
  }

  emitMessage(data: unknown): void {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

function installFakeWebSocket(): () => void {
  FakeWebSocket.instances = [];
  const target = globalThis as unknown as { WebSocket: typeof WebSocket };
  const previous = target.WebSocket;
  target.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
  return () => {
    target.WebSocket = previous;
    FakeWebSocket.instances = [];
  };
}

test('summary adapter connects only to the backend /ws/summary route', () => {
  const restore = installFakeWebSocket();
  try {
    const ws = new VictorSummaryWS();
    ws.connect('https://api.example.test', { mode: 'summary' });

    assert.equal(FakeWebSocket.instances.length, 1);
    assert.equal(
      FakeWebSocket.instances[0].url,
      'wss://api.example.test/ws/summary?mode=summary&full_every=10',
    );
    ws.disconnect();
  } finally {
    restore();
  }
});

test('complete summary messages are exposed to the reconciliation-facing observation callback', () => {
  const restore = installFakeWebSocket();
  try {
    const ws = new VictorSummaryWS();
    const observed: Array<{ message: SummaryMessage; receivedAtMs: number }> = [];
    ws.onObservation((message, receivedAtMs) => observed.push({ message, receivedAtMs }));
    ws.connect('https://api.example.test', { mode: 'summary' });

    const message: SummaryMessage = {
      type: 'summary',
      data: { chain: 'base', block: 123, opp_count: 4 },
    };
    FakeWebSocket.instances[0].emitOpen();
    FakeWebSocket.instances[0].emitMessage(message);

    assert.equal(observed.length, 1);
    assert.deepEqual(observed[0].message, message);
    assert.equal(Number.isFinite(observed[0].receivedAtMs), true);
    ws.disconnect();
  } finally {
    restore();
  }
});

test('malformed websocket payloads are rejected and never reach reconciliation', () => {
  const restore = installFakeWebSocket();
  try {
    const ws = new VictorSummaryWS();
    const observed: SummaryMessage[] = [];
    const errors: string[] = [];
    ws.onObservation((message) => observed.push(message));
    ws.onError((error) => errors.push(error));
    ws.connect('https://api.example.test', { mode: 'summary' });

    FakeWebSocket.instances[0].emitMessage({ type: 'summary', data: null });
    FakeWebSocket.instances[0].emitMessage({ type: 'unknown', data: {} });

    assert.equal(observed.length, 0);
    assert.equal(errors.length, 2);
    assert.deepEqual(errors, ['ws_invalid_message', 'ws_invalid_message']);
    ws.disconnect();
  } finally {
    restore();
  }
});

test('disconnect is terminal for the current adapter lifecycle', () => {
  const restore = installFakeWebSocket();
  try {
    const ws = new VictorSummaryWS();
    ws.connect('https://api.example.test', { mode: 'summary' });
    const socket = FakeWebSocket.instances[0];
    ws.disconnect();

    assert.equal(socket.closed, true);
    socket.onclose?.();
    assert.equal(FakeWebSocket.instances.length, 1);
  } finally {
    restore();
  }
});
