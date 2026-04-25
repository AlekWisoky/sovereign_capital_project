import React from "react";
import { View, Text, Pressable } from "react-native";
import { useTheme } from "../../utils/useTheme";

export function SegmentedTabs<T extends string>(props: {
  options: readonly T[];
  value: T;
  onChange: (v: T) => void;
}) {
  const theme = useTheme();
  return (
    <View style={{ flexDirection: "row", padding: 4, borderRadius: theme.radii.pill, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
      {props.options.map((opt) => {
        const active = opt === props.value;
        return (
          <Pressable
            key={opt}
            onPress={() => props.onChange(opt)}
            style={{
              flex: 1,
              paddingVertical: 8,
              borderRadius: theme.radii.pill,
              backgroundColor: active ? theme.colors.surface2 : "transparent",
              alignItems: "center",
            }}
          >
            <Text style={{ color: active ? theme.colors.text : theme.colors.textMuted, ...theme.typography.mono }}>{opt}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}
