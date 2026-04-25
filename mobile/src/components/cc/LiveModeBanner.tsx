import React from "react";
import { Text, View } from "react-native";
import { useTheme } from "../../utils/useTheme";

export function LiveModeBanner(props: { mode: "live" | "backend-mock" | "demo"; sourceLabel?: string; note?: string }) {
  const theme = useTheme();
  const tone = props.mode === "live" ? theme.colors.good : props.mode === "backend-mock" ? theme.colors.warn : theme.colors.danger;
  const bg = props.mode === "live" ? "rgba(34,197,94,0.10)" : props.mode === "backend-mock" ? "rgba(251,191,36,0.10)" : "rgba(251,113,133,0.10)";
  const title = props.mode === "live" ? "LIVE BACKEND MODE" : props.mode === "backend-mock" ? "BACKEND CONNECTED · DEMO DATA" : "MOCK / DEMO MODE";
  const note = props.note || (props.mode === "live" ? "Actions and analytics reflect connected backend state." : props.mode === "backend-mock" ? "Backend is reachable, but the screen is showing fallback/demo-style state for missing live fields." : "No live backend control or profitability claims should be assumed in demo mode.");
  return (
    <View style={{ padding: 12, borderRadius: theme.radii.lg, borderWidth: 1, borderColor: tone, backgroundColor: bg }}>
      <Text style={{ color: tone, fontWeight: "900", letterSpacing: 0.4 }}>{title}</Text>
      <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
        {note}{props.sourceLabel ? ` Source: ${props.sourceLabel}.` : ""}
      </Text>
    </View>
  );
}
