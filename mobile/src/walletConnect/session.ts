export type Eip1193Provider = {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
};

type Listener = () => void;

let provider: Eip1193Provider | null = null;
let address = "";
let connected = false;
let openWallet: (() => Promise<unknown> | void) | null = null;
const listeners = new Set<Listener>();

export function setWalletConnectSession(next: {
  provider?: Eip1193Provider | null;
  address?: string | null;
  isConnected?: boolean;
  open?: (() => Promise<unknown> | void) | null;
}): void {
  provider = next.provider ?? null;
  address = String(next.address ?? "").trim();
  connected = Boolean(next.isConnected && provider);
  openWallet = next.open ?? null;
  listeners.forEach((listener) => listener());
}

export function subscribeWalletConnect(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function walletConnectState(): { connected: boolean; address: string } {
  return { connected, address };
}

export async function connectWalletConnect(): Promise<void> {
  if (!openWallet) throw new Error("WalletConnect is unavailable");
  await openWallet();
}

export async function sendWalletConnectTransaction(tx: Record<string, unknown>): Promise<string> {
  if (!provider) throw new Error("Connect an external wallet first");
  const result = await provider.request({ method: "eth_sendTransaction", params: [tx] });
  if (typeof result !== "string" || !/^0x[0-9a-fA-F]{64}$/.test(result)) {
    throw new Error("Wallet returned an invalid transaction hash");
  }
  return result;
}
