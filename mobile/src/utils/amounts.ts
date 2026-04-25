// Lightweight units helpers (no external deps)
// - parseUnits: human string -> raw integer string
// - formatUnits: raw integer string -> human string

export function clampDecimals(d: number): number {
  const n = Number.isFinite(d) ? Math.trunc(d) : 0;
  if (n < 0) return 0;
  if (n > 36) return 36; // pragmatic upper bound
  return n;
}

function pow10(decimals: number): bigint {
  const d = clampDecimals(decimals);
  let x = 1n;
  for (let i = 0; i < d; i++) x *= 10n;
  return x;
}

export type ParseUnitsResult = {
  ok: boolean;
  raw: string;
  truncated: boolean;
  error?: string;
};

export function parseUnits(human: string, decimals: number): ParseUnitsResult {
  const d = clampDecimals(decimals);
  const s = String(human ?? "").trim();
  if (!s) return { ok: true, raw: "0", truncated: false };

  // Accept: "123", "123.", "123.45", ".45" (normalize to 0.45)
  const norm = s.startsWith(".") ? `0${s}` : s;
  if (!/^\d+(\.\d+)?\.?$/.test(norm)) {
    return { ok: false, raw: "0", truncated: false, error: "Invalid number format" };
  }

  const parts = norm.split(".");
  const intPart = parts[0] || "0";
  const fracPartRaw = parts.length > 1 ? (parts[1] || "") : "";
  const fracPart = fracPartRaw.replace(/\D/g, "");

  const truncated = fracPart.length > d;
  const fracUse = d === 0 ? "" : fracPart.slice(0, d);
  const fracPadded = d === 0 ? "" : fracUse.padEnd(d, "0");

  try {
    const biInt = BigInt(intPart || "0");
    const biFrac = d === 0 ? 0n : BigInt(fracPadded || "0");
    const raw = biInt * pow10(d) + biFrac;
    return { ok: true, raw: raw.toString(10), truncated };
  } catch {
    return { ok: false, raw: "0", truncated: false, error: "Could not parse number" };
  }
}

export function formatUnits(raw: string, decimals: number, maxFractionDigits = 8): string {
  const d = clampDecimals(decimals);
  const s = String(raw ?? "0").trim();
  if (!s) return "0";
  let bi: bigint;
  try {
    bi = BigInt(s);
  } catch {
    return "0";
  }
  if (d === 0) return bi.toString(10);

  const base = pow10(d);
  const intPart = bi / base;
  const fracPart = (bi % base).toString(10).padStart(d, "0");

  const maxF = Math.max(0, Math.min(maxFractionDigits, d));
  const cut = fracPart.slice(0, maxF);
  const trimmed = cut.replace(/0+$/, "");
  return trimmed ? `${intPart.toString(10)}.${trimmed}` : intPart.toString(10);
}
