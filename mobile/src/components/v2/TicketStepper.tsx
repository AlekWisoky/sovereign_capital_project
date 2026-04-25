import React from "react";
import { View, Text } from "react-native";
import { useTheme } from "../../utils/useTheme";

export type TicketStage = "NEW" | "SIMULATED" | "PREFLIGHT" | "EXEC_SENT" | "MINED" | "DECODED" | "FAILED";

const STAGES: TicketStage[] = ["NEW", "SIMULATED", "PREFLIGHT", "EXEC_SENT", "MINED", "DECODED"];

export function TicketStepper(props: { stage: TicketStage }) {
  const theme = useTheme();
  const idx = STAGES.indexOf(props.stage);
  const failed = props.stage === "FAILED";
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginTop: 10 }}>
      {STAGES.map((s, i) => {
        const active = !failed && i <= idx;
        const dot = failed ? theme.colors.danger : active ? theme.colors.cyan : theme.colors.border;
        return (
          <View key={s} style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <View style={{ width: 8, height: 8, borderRadius: 999, backgroundColor: dot }} />
            <Text style={{ color: active ? theme.colors.textMuted : theme.colors.textFaint, ...theme.typography.mono }}>{s}</Text>
            {i < STAGES.length - 1 ? <View style={{ width: 10, height: 1, backgroundColor: theme.colors.border }} /> : null}
          </View>
        );
      })}

      {failed ? <Text style={{ color: theme.colors.danger, marginLeft: 6, ...theme.typography.mono }}>FAILED</Text> : null}
    </View>
  );
}
