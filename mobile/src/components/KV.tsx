import React from "react";
import { Text, View } from "react-native";
import { theme } from "../utils/theme";

export function KV({ k, v }: { k: string; v: string }) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 6 }}>
      <Text style={{ color: theme.sub, fontSize: 12 }}>{k}</Text>
      <Text style={{ color: theme.text, fontSize: 12, fontWeight: "700" }}>{v}</Text>
    </View>
  );
}
