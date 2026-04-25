import React from "react";
import { Pressable, Text } from "react-native";
import { theme } from "../utils/theme";

export function Button({
  title,
  onPress,
  kind = "primary",
  disabled = false,
}: {
  title: string;
  onPress: () => void;
  kind?: "primary" | "ghost" | "danger";
  disabled?: boolean;
}) {
  const bg =
    kind === "danger" ? "#3b0a0a" :
    kind === "ghost" ? theme.card2 :
    theme.glow;
  const border = kind === "danger" ? "#7f1d1d" : (kind === "primary" ? theme.accent : theme.border);

  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => ({
        marginTop: 10,
        paddingVertical: 12,
        paddingHorizontal: 14,
        borderRadius: 16,
        backgroundColor: bg,
        borderWidth: 1,
        borderColor: border,
        opacity: disabled ? 0.55 : pressed ? 0.8 : 1,
        shadowColor: "#000",
        shadowOpacity: kind === "primary" ? 0.25 : 0.12,
        shadowRadius: kind === "primary" ? 14 : 10,
        shadowOffset: { width: 0, height: 8 },
        elevation: kind === "primary" ? 4 : 2,
      })}
    >
      <Text style={{ color: theme.text, fontWeight: "900", letterSpacing: 0.25 }}>{title}</Text>
    </Pressable>
  );
}
