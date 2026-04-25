import React from "react";
import { View } from "react-native";
import { theme } from "../utils/theme";

export function Card({ children, pad = 14 }: { children: React.ReactNode; pad?: number }) {
  return (
    <View
      style={{
        backgroundColor: theme.card,
        borderColor: theme.border,
        borderWidth: 1,
        borderRadius: 18,
        padding: pad,
        marginTop: 12,
        shadowColor: "#000",
        shadowOpacity: 0.2,
        shadowRadius: 12,
        shadowOffset: { width: 0, height: 6 },
        elevation: 3,
      }}
    >
      {children}
    </View>
  );
}
