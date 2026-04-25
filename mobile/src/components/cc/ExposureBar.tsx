import React from "react";
import { View, Text } from "react-native";
import { useTheme } from "../../utils/useTheme";
import type { ExposureState } from "../../commandCenter/types";

function clampPct(n: number): number {
  if (!isFinite(n)) return 0;
  return Math.max(0, Math.min(100, n));
}

export function ExposureBar({ exposure }: { exposure: ExposureState }) {
  const theme = useTheme();
  const a = clampPct(exposure.activePct);
  const s = clampPct(exposure.sandboxPct);
  const i = clampPct(exposure.idlePct);
  const r = clampPct(exposure.atRiskPct);
  const total = Math.max(1, a + s + i + r);
  const w = (x: number) => `${(100 * x) / total}%`;

  return (
    <View>
      <View style={{ flexDirection: "row", height: 12, borderRadius: theme.radii.pill, overflow: "hidden", borderWidth: 1, borderColor: theme.colors.border }}>
        <View style={{ width: w(a), backgroundColor: theme.colors.cyan }} />
        <View style={{ width: w(s), backgroundColor: theme.colors.violet }} />
        <View style={{ width: w(i), backgroundColor: theme.colors.surface2 }} />
        <View style={{ width: w(r), backgroundColor: theme.colors.warn }} />
      </View>
      <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 10 }}>
        <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Active {a.toFixed(0)}%</Text>
        <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Sandbox {s.toFixed(0)}%</Text>
        <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Idle {i.toFixed(0)}%</Text>
        <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>At‑Risk {r.toFixed(0)}%</Text>
      </View>
    </View>
  );
}
