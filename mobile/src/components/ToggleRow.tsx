import React from "react";
import { Switch, Text, View } from "react-native";
import { theme } from "../utils/theme";

export function ToggleRow({ label, value, onValueChange }: { label: string; value: boolean; onValueChange: (v: boolean) => void }) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 10 }}>
      <Text style={{ color: theme.text, fontWeight: "600" }}>{label}</Text>
      <Switch value={value} onValueChange={onValueChange} />
    </View>
  );
}
