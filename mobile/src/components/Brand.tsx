import React from "react";
import { Text, View } from "react-native";
import { theme } from "../utils/theme";

export function BrandMark({ subtitle }: { subtitle?: string }) {
  return (
    <View style={{ marginBottom: 14 }}>
      <Text style={{ color: theme.text, fontSize: 30, fontWeight: "900", letterSpacing: 0.5 }}>
        x∆v
      </Text>
      {subtitle ? (
        <Text style={{ color: theme.sub, marginTop: 2, fontWeight: "600" }}>{subtitle}</Text>
      ) : null}
    </View>
  );
}
