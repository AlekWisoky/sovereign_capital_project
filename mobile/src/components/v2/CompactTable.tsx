import React from "react";
import { View, Text, Pressable } from "react-native";
import { useTheme } from "../../utils/useTheme";

export type CompactRow = {
  key: string;
  cols: [string, string, string, string];
  tone?: "neutral" | "good" | "warn" | "danger";
};

export function CompactTable(props: {
  header: [string, string, string, string];
  rows: readonly CompactRow[];
  onPressRow?: (key: string) => void;
}) {
  const theme = useTheme();
  const onPress = props.onPressRow;
  return (
    <View style={{ borderWidth: 1, borderColor: theme.colors.border, borderRadius: theme.radii.lg, overflow: "hidden" }}>
      <View style={{ flexDirection: "row", paddingVertical: 10, paddingHorizontal: 12, backgroundColor: theme.colors.surface2 }}>
        {props.header.map((h, i) => (
          <Text key={i} style={{ flex: 1, color: theme.colors.textFaint, ...theme.typography.mono }}>
            {h}
          </Text>
        ))}
      </View>

      {props.rows.map((r) => {
        const tone = r.tone ?? "neutral";
        const accent = tone === "good" ? theme.colors.good : tone === "warn" ? theme.colors.warn : tone === "danger" ? theme.colors.danger : theme.colors.textMuted;
        const row = (
          <View key={r.key} style={{ flexDirection: "row", paddingVertical: 12, paddingHorizontal: 12, backgroundColor: theme.colors.surface0, borderTopWidth: 1, borderTopColor: theme.colors.border }}>
            {r.cols.map((c, i) => (
              <Text key={i} style={{ flex: 1, color: i === 2 ? accent : theme.colors.textMuted, ...theme.typography.mono }}>
                {c}
              </Text>
            ))}
          </View>
        );
        return onPress ? (
          <Pressable key={r.key} onPress={() => onPress(r.key)}>{row}</Pressable>
        ) : (
          row
        );
      })}
    </View>
  );
}
