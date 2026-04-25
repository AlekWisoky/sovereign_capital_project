import React from "react";
import { View, Text } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useTheme } from "../../utils/useTheme";

export function BrandHeader(props: { title: string; subtitle?: string; rightTag?: string }) {
  const { title, subtitle, rightTag } = props;
  const theme = useTheme();
  return (
    <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: theme.spacing.md }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: theme.spacing.sm }}>
        <LinearGradient
          colors={[theme.colors.cyan, theme.colors.violet]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={{ minWidth: 46, height: 34, paddingHorizontal: 8, borderRadius: 12, alignItems: "center", justifyContent: "center" }}
        >
          <Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>x∆v</Text>
        </LinearGradient>

        <View>
          <Text style={{ color: theme.colors.text, ...theme.typography.title }}>{title}</Text>
          {subtitle ? <Text style={{ color: theme.colors.textMuted, marginTop: 2, ...theme.typography.body }}>{subtitle}</Text> : null}
        </View>
      </View>

      {rightTag ? (
        <View
          style={{
            paddingHorizontal: theme.spacing.sm,
            paddingVertical: 6,
            borderRadius: theme.radii.pill,
            borderWidth: 1,
            borderColor: theme.colors.border,
            backgroundColor: theme.colors.surface1,
          }}
        >
          <Text style={{ color: theme.colors.textMuted, ...theme.typography.mono }}>{rightTag}</Text>
        </View>
      ) : null}
    </View>
  );
}
