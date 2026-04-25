export function normalizeAddress(a: string): string {
  return String(a || "").trim().toLowerCase();
}

export function isHexAddress(a: string): boolean {
  const s = String(a || "").trim();
  return /^0x[0-9a-fA-F]{40}$/.test(s);
}

export function uniqAddresses(list: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const x of list || []) {
    const n = normalizeAddress(x);
    if (!n) continue;
    if (!seen.has(n)) {
      seen.add(n);
      out.push(n);
    }
  }
  return out;
}

export function toHex(n: number | string | bigint | null | undefined): string {
  if (n === null || n === undefined) return "0x0";
  if (typeof n === "string") {
    const s = n.trim();
    if (s.startsWith("0x")) return s;
    const bi = BigInt(s);
    return "0x" + bi.toString(16);
  }
  if (typeof n === "number") return "0x" + BigInt(n).toString(16);
  return "0x" + n.toString(16);
}
