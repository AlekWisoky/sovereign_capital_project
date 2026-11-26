"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.sendWalletConnectTransaction = exports.connectWalletConnect = exports.walletConnectState = exports.subscribeWalletConnect = exports.setWalletConnectSession = void 0;
let provider = null;
let address = "";
let connected = false;
let openWallet = null;
const listeners = new Set();
function setWalletConnectSession(next) {
    provider = next.provider ?? null;
    address = String(next.address ?? "").trim();
    connected = Boolean(next.isConnected && provider);
    openWallet = next.open ?? null;
    listeners.forEach((listener) => listener());
}
exports.setWalletConnectSession = setWalletConnectSession;
function subscribeWalletConnect(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
}
exports.subscribeWalletConnect = subscribeWalletConnect;
function walletConnectState() {
    return { connected, address, provider };
}
exports.walletConnectState = walletConnectState;
async function connectWalletConnect() {
    if (!openWallet)
        throw new Error("WalletConnect is unavailable");
    await openWallet();
}
exports.connectWalletConnect = connectWalletConnect;
async function sendWalletConnectTransaction(tx) {
    if (!provider)
        throw new Error("Connect an external wallet first");
    const result = await provider.request({ method: "eth_sendTransaction", params: [tx] });
    if (typeof result !== "string" || !/^0x[0-9a-fA-F]{64}$/.test(result)) {
        throw new Error("Wallet returned an invalid transaction hash");
    }
    return result;
}
exports.sendWalletConnectTransaction = sendWalletConnectTransaction;
