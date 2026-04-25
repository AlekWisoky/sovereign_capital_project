import React from "react";
import { View, Text } from "react-native";
import { useTheme } from "../../utils/useTheme";
import { SurfaceCard } from "./SurfaceCard";

export function StatTile(props: {
  label: string;
  value: string;
  hint?: string;
  tone?: "neutral" | "good" | "warn" | "danger";
}) {
  const theme = useTheme();
  const tone = props.tone ?? "neutral";
  const color =
    tone === "good" ? theme.colors.good : tone === "warn" ? theme.colors.warn : tone === "danger" ? theme.colors.danger : theme.colors.cyan;

  return (
    <SurfaceCard glow="none" style={{ flex: 1, minWidth: 155 }}>
      <Text style={{ color: theme.colors.textMuted, ...theme.typography.mono }}>{props.label}</Text>
      <Text style={{ color: theme.colors.text, fontSize: 20, fontWeight: "900", marginTop: 4 }}>{props.value}</Text>
      {props.hint ? <Text style={{ color, marginTop: 4, ...theme.typography.mono }}>{props.hint}</Text> : null}
    </SurfaceCard>
  );
}
