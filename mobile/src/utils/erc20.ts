import { isHexAddress, normalizeAddress } from "./eth";

export type Eip1193Provider = {
  request: (args: { method: string; params?: unknown[] | Record<string, unknown> }) => Promise<unknown>;
};

// ERC-20 selectors
const SEL_DECIMALS = "0x313ce567"; // decimals()
const SEL_SYMBOL = "0x95d89b41";   // symbol()

function strip0x(hex: string): string {
  const s = String(hex || "");
  return s.startsWith("0x") ? s.slice(2) : s;
}

function hexToBytes(hex: string): Uint8Array {
  const h = strip0x(hex);
  const len = Math.floor(h.length / 2);
  const out = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    out[i] = parseInt(h.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}

function bytesToUtf8(bytes: Uint8Array): string {
  try {
    // react-native supports TextDecoder in modern runtimes; fall back if missing.
    const TD = (globalThis as unknown as { TextDecoder?: typeof TextDecoder }).TextDecoder;
    if (TD) return new TD("utf-8").decode(bytes);
  } catch {}
  // naive fallback
  let s = "";
  for (const b of bytes) {
    if (b === 0) break;
    s += String.fromCharCode(b);
  }
  return s;
}

function decodeUint(hex: string): bigint | null {
  const h = strip0x(hex);
  if (!h) return null;
  try {
    return BigInt("0x" + h);
  } catch {
    return null;
  }
}

function decodeAbiString(retHex: string): string | null {
  const h = strip0x(retHex);
  if (!h) return null;

  // Some tokens return bytes32 for symbol()
  if (h.length === 64) {
    const b = hexToBytes("0x" + h);
    const s = bytesToUtf8(b).replace(/\u0000/g, "").trim();
    return s || null;
  }

  // Standard ABI encoding for string:
  // 0x
  // [0..32): offset
  // [offset..offset+32): length
  // [offset+32..]: data
  try {
    const bytes = hexToBytes("0x" + h);
    if (bytes.length < 64) return null;

    const view = (start: number, end: number) => bytes.slice(start, end);
    const toBig = (b: Uint8Array) => {
      let x = 0n;
      for (const v of b) x = (x << 8n) + BigInt(v);
      return x;
    };

    const offset = Number(toBig(view(0, 32)));
    if (!Number.isFinite(offset) || offset < 0 || offset + 32 > bytes.length) return null;

    const len = Number(toBig(view(offset, offset + 32)));
    if (!Number.isFinite(len) || len < 0) return null;

    const dataStart = offset + 32;
    const dataEnd = Math.min(bytes.length, dataStart + len);
    if (dataEnd <= dataStart) return null;

    const s = bytesToUtf8(view(dataStart, dataEnd)).trim();
    return s || null;
  } catch {
    return null;
  }
}

async function ethCall(provider: Eip1193Provider, to: string, data: string): Promise<string> {
  // WalletConnect provider.request supports eth_call
  const res = await provider.request({
    method: "eth_call",
    params: [{ to, data }, "latest"],
  });
  return String(res || "0x");
}

export async function fetchTokenMeta(provider: Eip1193Provider, tokenAddress: string): Promise<{ decimals?: number; symbol?: string }> {
  const token = normalizeAddress(tokenAddress);
  if (!provider || !isHexAddress(token)) return {};

  const out: { decimals?: number; symbol?: string } = {};

  // decimals()
  try {
    const ret = await ethCall(provider, token, SEL_DECIMALS);
    const bi = decodeUint(ret);
    if (bi !== null) {
      const n = Number(bi);
      if (Number.isFinite(n) && n >= 0 && n <= 255) out.decimals = n;
    }
  } catch {}

  // symbol()
  try {
    const ret = await ethCall(provider, token, SEL_SYMBOL);
    const sym = decodeAbiString(ret);
    if (sym) out.symbol = sym;
  } catch {}

  return out;
}
