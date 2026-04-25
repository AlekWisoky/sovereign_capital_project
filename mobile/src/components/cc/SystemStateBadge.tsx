import React from "react";
import { View, Text } from "react-native";
import { useTheme } from "../../utils/useTheme";
import type { SystemState } from "../../commandCenter/types";

function labelFor(s: SystemState): string {
  if (s === "active") return "ACTIVE";
  if (s === "defensive") return "DEFENSIVE";
  if (s === "sandbox_only") return "SANDBOX ONLY";
  return "PAUSED";
}

export function SystemStateBadge({ state }: { state: SystemState }) {
  const theme = useTheme();
  const color = state === "active" ? theme.colors.ok : state === "paused" ? theme.colors.danger : theme.colors.warn;
  const bg = state === "active" ? "rgba(52, 211, 153, 0.14)" : state === "paused" ? "rgba(251, 113, 133, 0.14)" : "rgba(251, 191, 36, 0.12)";
  return (
    <View style={{
      paddingVertical: 6,
      paddingHorizontal: 10,
      borderRadius: theme.radii.pill,
      borderWidth: 1,
      borderColor: color,
      backgroundColor: bg,
    }}>
      <Text style={{ color, fontWeight: "900", letterSpacing: 0.5 }}>{labelFor(state)}</Text>
    </View>
  );
}
