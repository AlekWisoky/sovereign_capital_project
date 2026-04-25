import React from "react";
import { Modal, View, Text, ScrollView, Pressable } from "react-native";
import { useTheme } from "../../utils/useTheme";
import { SurfaceCard } from "./SurfaceCard";
import type { JsonValue } from "../../utils/types";

function jsonPretty(v: JsonValue | undefined): string {
  try {
    return JSON.stringify(v ?? null, null, 2);
  } catch {
    return "(unserializable)";
  }
}

export function ReceiptDrawer(props: { visible: boolean; title: string; payload?: JsonValue; onClose: () => void }) {
  const theme = useTheme();
  return (
    <Modal visible={props.visible} animationType="slide" transparent onRequestClose={props.onClose}>
      <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.65)", justifyContent: "flex-end" }}>
        <SurfaceCard glow="cyan" style={{ borderBottomLeftRadius: 0, borderBottomRightRadius: 0, width: "100%" }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>{props.title}</Text>
            <Pressable onPress={props.onClose} style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: theme.radii.pill, backgroundColor: theme.colors.surface2 }}>
              <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>Close</Text>
            </Pressable>
          </View>
          <ScrollView style={{ marginTop: theme.spacing.md, maxHeight: 480 }}>
            <Text style={{ color: theme.colors.textMuted, fontFamily: "monospace" }}>{jsonPretty(props.payload)}</Text>
          </ScrollView>
        </SurfaceCard>
      </View>
    </Modal>
  );
}
