export type ThemeName = "cyan_ledger" | "violet_pulse" | "matrix_emerald";

export type Theme = {
  name: ThemeName;
  colors: {
    bg0: string;
    bg1: string;
    surface0: string;
    surface1: string;
    surface2: string;
    border: string;
    text: string;
    textMuted: string;
    textFaint: string;

    cyan: string;
    violet: string;
    good: string;
    warn: string;
    danger: string;

    // charts
    chartFill0: string;
    chartFill1: string;
    chartLine: string;

    // status
    ok: string;
    bad: string;
    neutral: string;
  };
  spacing: {
    xs: number;
    sm: number;
    md: number;
    lg: number;
    xl: number;
  };
  radii: {
    sm: number;
    md: number;
    lg: number;
    pill: number;
  };
  typography: {
    title: { fontSize: number; fontWeight: "700" | "800" | "900" };
    h1: { fontSize: number; fontWeight: "700" | "800" | "900" };
    h2: { fontSize: number; fontWeight: "700" | "800" | "900" };
    body: { fontSize: number; fontWeight: "400" | "500" | "600" | "700" };
    mono: { fontSize: number; fontWeight: "400" | "500" | "600" | "700" };
  };
  shadow: {
    soft: {
      shadowColor: string;
      shadowOpacity: number;
      shadowRadius: number;
      shadowOffset: { width: number; height: number };
      elevation: number;
    };
  };
  glow: {
    cyan: string;
    violet: string;
  };
};

// Backwards compatible shape used by the legacy (v0.x) screens.
export type LegacyTheme = Omit<Theme, "glow"> & {
  bg: string;
  card: string;
  card2: string;
  accent: string;
  accent2: string;
  border: string;
  text: string;
  sub: string;
  glow: string;
  danger: string;
  warn: string;
  good: string;
};

const base = {
  spacing: { xs: 6, sm: 10, md: 14, lg: 18, xl: 24 },
  radii: { sm: 10, md: 14, lg: 18, pill: 999 },
  typography: {
    title: { fontSize: 22, fontWeight: "900" as const },
    h1: { fontSize: 18, fontWeight: "900" as const },
    h2: { fontSize: 16, fontWeight: "800" as const },
    body: { fontSize: 14, fontWeight: "500" as const },
    mono: { fontSize: 12, fontWeight: "600" as const },
  },
  shadow: {
    soft: {
      shadowColor: "#000000",
      shadowOpacity: 0.25,
      shadowRadius: 14,
      shadowOffset: { width: 0, height: 8 },
      elevation: 6,
    },
  },
} as const;

export const THEMES: Record<ThemeName, Theme> = {
  cyan_ledger: {
    name: "cyan_ledger",
    colors: {
      bg0: "#070A12",
      bg1: "#0A1022",
      surface0: "#0D152B",
      surface1: "#0B1220",
      surface2: "#0F1B33",
      border: "#1E2A45",
      text: "#EAF2FF",
      textMuted: "#A2B1CC",
      textFaint: "#6F7F9F",

      cyan: "#22D3EE",
      violet: "#A78BFA",
      good: "#34D399",
      warn: "#FBBF24",
      danger: "#FB7185",

      chartFill0: "rgba(34, 211, 238, 0.18)",
      chartFill1: "rgba(167, 139, 250, 0.10)",
      chartLine: "#22D3EE",

      ok: "#34D399",
      bad: "#FB7185",
      neutral: "#A2B1CC",
    },
    glow: { cyan: "rgba(34, 211, 238, 0.22)", violet: "rgba(167, 139, 250, 0.18)" },
    ...base,
  },
  violet_pulse: {
    name: "violet_pulse",
    colors: {
      bg0: "#070813",
      bg1: "#120A22",
      surface0: "#141029",
      surface1: "#0F0C1F",
      surface2: "#1B1440",
      border: "#2B245C",
      text: "#F3EEFF",
      textMuted: "#B9A9D9",
      textFaint: "#7A6F9A",

      cyan: "#22D3EE",
      violet: "#C4B5FD",
      good: "#34D399",
      warn: "#FBBF24",
      danger: "#FB7185",

      chartFill0: "rgba(196, 181, 253, 0.16)",
      chartFill1: "rgba(34, 211, 238, 0.10)",
      chartLine: "#C4B5FD",

      ok: "#34D399",
      bad: "#FB7185",
      neutral: "#B9A9D9",
    },
    glow: { cyan: "rgba(34, 211, 238, 0.18)", violet: "rgba(196, 181, 253, 0.22)" },
    ...base,
  },
  matrix_emerald: {
    name: "matrix_emerald",
    colors: {
      bg0: "#050A08",
      bg1: "#071C14",
      surface0: "#0A1510",
      surface1: "#07110D",
      surface2: "#0A2A1E",
      border: "#104434",
      text: "#E7FFF7",
      textMuted: "#A6D5C4",
      textFaint: "#6FA595",

      cyan: "#2DD4BF",
      violet: "#34D399",
      good: "#34D399",
      warn: "#FBBF24",
      danger: "#FB7185",

      chartFill0: "rgba(45, 212, 191, 0.16)",
      chartFill1: "rgba(52, 211, 153, 0.10)",
      chartLine: "#2DD4BF",

      ok: "#34D399",
      bad: "#FB7185",
      neutral: "#A6D5C4",
    },
    glow: { cyan: "rgba(45, 212, 191, 0.20)", violet: "rgba(52, 211, 153, 0.18)" },
    ...base,
  },
};

export function getTheme(name?: ThemeName | string | null): Theme {
  const key = String(name || "cyan_ledger") as ThemeName;
  return THEMES[key] ?? THEMES.cyan_ledger;
}

// Backwards-compatible default export used by legacy screens.
const t = getTheme("cyan_ledger");
export const theme: LegacyTheme = {
  ...t,
  bg: t.colors.bg0,
  card: t.colors.surface0,
  card2: t.colors.surface1,
  accent: t.colors.cyan,
  accent2: t.colors.violet,
  border: t.colors.border,
  text: t.colors.text,
  sub: t.colors.textMuted,
  glow: t.glow.cyan,
  danger: t.colors.danger,
  warn: t.colors.warn,
  good: t.colors.good,
};
