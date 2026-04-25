import React from "react";
import { View, StyleProp, ViewStyle } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useTheme } from "../../utils/useTheme";

export function SurfaceCard(props: { children: React.ReactNode; glow?: "cyan" | "violet" | "none"; style?: StyleProp<ViewStyle> }) {
  const theme = useTheme();
  const glow = props.glow ?? "none";
  const outerBorder = glow === "cyan" ? theme.glow.cyan : glow === "violet" ? theme.glow.violet : "rgba(255,255,255,0.06)";
  const innerBg = theme.colors.surface0;

  return (
    <View
      style={[
        {
          borderRadius: theme.radii.lg,
          padding: 1,
          backgroundColor: outerBorder,
          ...theme.shadow.soft,
        },
        props.style,
      ]}
    >
      <LinearGradient
        colors={[innerBg, theme.colors.surface1]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={{
          borderRadius: theme.radii.lg,
          padding: theme.spacing.md,
          borderWidth: 1,
          borderColor: theme.colors.border,
        }}
      >
        {props.children}
      </LinearGradient>
    </View>
  );
}
