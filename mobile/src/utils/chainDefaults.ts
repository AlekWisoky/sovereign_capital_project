import { normalizeAddress } from "./eth";

// Convenience defaults (user can override in UI)
export const WRAPPED_NATIVE: Record<string, string> = {
  ethereum: "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", // WETH
  arbitrum: "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1", // WETH
  optimism: "0x4200000000000000000000000000000000000006", // WETH
  base: "0x4200000000000000000000000000000000000006",     // WETH
  polygon: "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",  // WETH
};

export function defaultWrapped(chain: string): string {
  const c = String(chain || "").toLowerCase();
  const a = WRAPPED_NATIVE[c];
  return normalizeAddress(a || "") || "";
}
