import React from "react";
import { View, Text } from "react-native";
import { useTheme } from "../../utils/useTheme";

export function TopStatusBar(props: {
  title: string;
  subtitle?: string;
  rightTag?: string;
  live?: boolean;
}) {
  const theme = useTheme();
  return (
    <View style={{
      paddingVertical: 10,
      paddingHorizontal: 14,
      borderRadius: theme.radii.lg,
      backgroundColor: theme.colors.bg1,
      borderWidth: 1,
      borderColor: theme.colors.border,
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
    }}>
      <View style={{ flex: 1, paddingRight: 12 }}>
        <Text style={{ color: theme.colors.text, ...theme.typography.title }}>{props.title}</Text>
        {props.subtitle ? (
          <Text style={{ color: theme.colors.textMuted, marginTop: 2, ...theme.typography.body }}>{props.subtitle}</Text>
        ) : null}
      </View>

      <View style={{ alignItems: "flex-end" }}>
        {props.live ? (
          <View style={{
            paddingVertical: 4,
            paddingHorizontal: 10,
            borderRadius: theme.radii.pill,
            borderWidth: 1,
            borderColor: theme.colors.cyan,
            backgroundColor: theme.glow.cyan,
            marginBottom: 6,
          }}>
            <Text style={{ color: theme.colors.cyan, fontWeight: "900" }}>LIVE</Text>
          </View>
        ) : null}
        {props.rightTag ? (
          <Text style={{ color: theme.colors.textFaint, fontWeight: "800" }}>{props.rightTag}</Text>
        ) : null}
      </View>
    </View>
  );
}
