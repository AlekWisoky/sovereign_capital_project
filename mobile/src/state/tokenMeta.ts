import AsyncStorage from "@react-native-async-storage/async-storage";
import { normalizeAddress } from "../utils/eth";

export type TokenMeta = {
  address: string;
  decimals: number;
  symbol?: string;
  source: "chain" | "manual";
  updated_at_ms: number;
};

const KEY = "victor.tokenMeta";

type TokenMetaMap = Record<string, TokenMeta>;

async function readAll(): Promise<TokenMetaMap> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) return {};
    const obj = JSON.parse(raw);
    if (!obj || typeof obj !== "object") return {};
    return obj as TokenMetaMap;
  } catch {
    return {};
  }
}

async function writeAll(map: TokenMetaMap): Promise<void> {
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(map));
  } catch {}
}

export async function getTokenMeta(address: string): Promise<TokenMeta | null> {
  const a = normalizeAddress(address);
  if (!a) return null;
  const map = await readAll();
  return map[a] || null;
}

export async function upsertTokenMeta(meta: Omit<TokenMeta, "address" | "updated_at_ms"> & { address: string }): Promise<TokenMeta> {
  const a = normalizeAddress(meta.address);
  const map = await readAll();
  const next: TokenMeta = {
    address: a,
    decimals: Number(meta.decimals),
    symbol: meta.symbol ? String(meta.symbol) : undefined,
    source: meta.source,
    updated_at_ms: Date.now(),
  };
  map[a] = next;
  await writeAll(map);
  return next;
}

export async function deleteTokenMeta(address: string): Promise<void> {
  const a = normalizeAddress(address);
  const map = await readAll();
  if (map[a]) {
    delete map[a];
    await writeAll(map);
  }
}
