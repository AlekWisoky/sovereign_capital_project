import React, { useState } from "react";
import { Modal, View, Text, Pressable, TextInput } from "react-native";
import { useTheme } from "../../utils/useTheme";
import { SurfaceCard } from "./SurfaceCard";

export function JsonImportDialog(props: { visible: boolean; onClose: () => void; onImport: (text: string) => void }) {
  const theme = useTheme();
  const [text, setText] = useState("");

  return (
    <Modal visible={props.visible} transparent animationType="fade" onRequestClose={props.onClose}>
      <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.55)", justifyContent: "center", padding: theme.spacing.lg }}>
        <SurfaceCard glow="none" style={{ padding: theme.spacing.lg }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Import ticket JSON</Text>
          <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
            Paste a previously exported ticket bundle.
          </Text>

          <TextInput
            value={text}
            onChangeText={setText}
            placeholder="{ ... }"
            placeholderTextColor={theme.colors.textFaint}
            multiline
            style={{
              marginTop: theme.spacing.md,
              height: 160,
              padding: 12,
              borderRadius: theme.radii.md,
              borderWidth: 1,
              borderColor: theme.colors.border,
              color: theme.colors.text,
              backgroundColor: theme.colors.surface1,
              fontFamily: "monospace",
              textAlignVertical: "top",
            }}
          />

          <View style={{ flexDirection: "row", gap: 10, marginTop: theme.spacing.md }}>
            <Pressable
              onPress={props.onClose}
              style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface2, alignItems: "center" }}
            >
              <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>Cancel</Text>
            </Pressable>
            <Pressable
              onPress={() => {
                props.onImport(text);
                setText("");
              }}
              style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.cyan, alignItems: "center" }}
            >
              <Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>Import</Text>
            </Pressable>
          </View>
        </SurfaceCard>
      </View>
    </Modal>
  );
}
