import React, { useEffect, useState } from "react";
import { Modal, View, Text, Pressable, TextInput } from "react-native";
import { useTheme } from "../../utils/useTheme";
import { SurfaceCard } from "../v2/SurfaceCard";

export function ConfirmReasonDialog(props: {
  visible: boolean;
  title: string;
  body?: string;
  tone?: "neutral" | "danger";
  confirmText?: string;
  cancelText?: string;
  requireReason?: boolean;
  onCancel: () => void;
  onConfirm: (reason: string) => void;
}) {
  const theme = useTheme();
  const [reason, setReason] = useState("");
  useEffect(() => {
    if (props.visible) setReason("");
  }, [props.visible]);

  const tone = props.tone ?? "neutral";
  const confirmBg = tone === "danger" ? theme.colors.danger : theme.colors.cyan;
  const ok = !props.requireReason || reason.trim().length >= 6;

  return (
    <Modal visible={props.visible} animationType="fade" transparent onRequestClose={props.onCancel}>
      <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.65)", alignItems: "center", justifyContent: "center", padding: theme.spacing.lg }}>
        <SurfaceCard glow="violet" style={{ width: "100%" }}>
          <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>{props.title}</Text>
          {props.body ? <Text style={{ color: theme.colors.textMuted, marginTop: 8, ...theme.typography.body }}>{props.body}</Text> : null}

          <Text style={{ color: theme.colors.textFaint, marginTop: theme.spacing.md, ...theme.typography.mono }}>Reason (required; ≥ 6 chars)</Text>
          <TextInput
            value={reason}
            onChangeText={setReason}
            placeholder="Why are you doing this?"
            placeholderTextColor={theme.colors.textFaint}
            style={{
              marginTop: 8,
              padding: 12,
              borderRadius: theme.radii.md,
              borderWidth: 1,
              borderColor: theme.colors.border,
              color: theme.colors.text,
              backgroundColor: theme.colors.surface1,
            }}
          />

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
              <Text style={{ color: theme.colors.textMuted, fontWeight: "800" }}>{props.cancelText ?? "Cancel"}</Text>
            </Pressable>

            <Pressable
              onPress={() => ok && props.onConfirm(reason.trim())}
              style={{
                flex: 1,
                paddingVertical: 12,
                borderRadius: theme.radii.md,
                backgroundColor: ok ? confirmBg : theme.colors.surface2,
                alignItems: "center",
              }}
            >
              <Text style={{ color: ok ? theme.colors.bg0 : theme.colors.textFaint, fontWeight: "900" }}>{props.confirmText ?? "Confirm"}</Text>
            </Pressable>
          </View>
        </SurfaceCard>
      </View>
    </Modal>
  );
}
