import React from "react";
import { Modal, View, Text, Pressable } from "react-native";
import { useTheme } from "../../utils/useTheme";
import { SurfaceCard } from "./SurfaceCard";

export function ConfirmDialog(props: {
  visible: boolean;
  title: string;
  body?: string;
  confirmText?: string;
  cancelText?: string;
  tone?: "neutral" | "danger";
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const theme = useTheme();
  const confirmText = props.confirmText ?? "Confirm";
  const cancelText = props.cancelText ?? "Cancel";
  const tone = props.tone ?? "neutral";
  const confirmBg = tone === "danger" ? theme.colors.danger : theme.colors.cyan;

  return (
    <Modal visible={props.visible} animationType="fade" transparent onRequestClose={props.onCancel}>
      <View
        style={{
          flex: 1,
          backgroundColor: "rgba(0,0,0,0.65)",
          alignItems: "center",
          justifyContent: "center",
          padding: theme.spacing.lg,
        }}
      >
        <SurfaceCard glow="violet" style={{ width: "100%" }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>{props.title}</Text>
          {props.body ? <Text style={{ color: theme.colors.textMuted, marginTop: 8, ...theme.typography.body }}>{props.body}</Text> : null}

          <View style={{ flexDirection: "row", gap: theme.spacing.sm, marginTop: theme.spacing.lg }}>
            <Pressable
              onPress={props.onCancel}
              style={{
                flex: 1,
                paddingVertical: 12,
                borderRadius: theme.radii.md,
                borderWidth: 1,
                borderColor: theme.colors.border,
                backgroundColor: theme.colors.surface1,
                alignItems: "center",
              }}
            >
              <Text style={{ color: theme.colors.textMuted, fontWeight: "800" }}>{cancelText}</Text>
            </Pressable>

            <Pressable
              onPress={props.onConfirm}
              style={{
                flex: 1,
                paddingVertical: 12,
                borderRadius: theme.radii.md,
                backgroundColor: confirmBg,
                alignItems: "center",
              }}
            >
              <Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>{confirmText}</Text>
            </Pressable>
          </View>
        </SurfaceCard>
      </View>
    </Modal>
  );
}
