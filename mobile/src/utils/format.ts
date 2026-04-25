export function fmtPct(x: number, digits: number = 1): string {
  if (!Number.isFinite(x)) return "–";
  return `${x.toFixed(digits)}%`;
}

export function fmtMs(x: number): string {
  if (!Number.isFinite(x)) return "–";
  if (x < 1000) return `${Math.round(x)}ms`;
  return `${(x / 1000).toFixed(2)}s`;
}

export function fmtUsd(x: number): string {
  if (!Number.isFinite(x)) return "–";
  const sign = x < 0 ? "-" : "";
  const ax = Math.abs(x);
  if (ax >= 1_000_000) return `${sign}$${(ax / 1_000_000).toFixed(2)}M`;
  if (ax >= 1_000) return `${sign}$${(ax / 1_000).toFixed(2)}k`;
  return `${sign}$${ax.toFixed(2)}`;
}

export function fmtCompact(x: number, digits: number = 2): string {
  if (!Number.isFinite(x)) return "–";
  const sign = x < 0 ? "-" : "";
  const ax = Math.abs(x);
  if (ax >= 1_000_000) return `${sign}${(ax / 1_000_000).toFixed(digits)}M`;
  if (ax >= 1_000) return `${sign}${(ax / 1_000).toFixed(digits)}k`;
  return `${sign}${ax.toFixed(digits)}`;
}

export function fmtShortHash(s: string, keep: number = 6): string {
  const v = String(s || "");
  if (v.length <= keep * 2) return v;
  return `${v.slice(0, keep)}…${v.slice(-keep)}`;
}

export function fmtTime(tsMs: number): string {
  const d = new Date(tsMs);
  if (Number.isNaN(d.getTime())) return "–";
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}
