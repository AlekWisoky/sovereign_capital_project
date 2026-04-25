import React, { useMemo, useState } from "react";
import { Modal, Pressable, ScrollView, Text, View } from "react-native";
import { useTheme } from "../../utils/useTheme";
import { useCommandCenter } from "../../commandCenter/useCommandCenter";
import type { ControlMode, ControlPatch } from "../../commandCenter/types";
import { SystemStateBadge } from "./SystemStateBadge";

function formatMode(mode: ControlMode | undefined): string {
  if (mode === "auto") return "Auto";
  if (mode === "assist") return "Assist";
  return "View Only";
}

function formatTime(tsMs?: number): string {
  if (!tsMs) return "—";
  try {
    return new Date(tsMs).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "—";
  }
}

export function ControlCenterSheet() {
  const theme = useTheme();
  const cc = useCommandCenter();
  const snap = cc.snapshot;
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState("");

  const mode = useMemo<ControlMode>(() => {
    return (snap?.controlMode ?? snap?.governance.controlMode ?? (snap?.governance.paused ? "view_only" : "assist")) as ControlMode;
  }, [snap]);

  async function applyQuick(patch: ControlPatch, reason: string) {
    setStatus("Applying…");
    try {
      const res = await cc.setControls(patch, reason);
      if (!res.ok) {
        setStatus(res.error ? `Failed · ${res.error}` : "Failed");
        return;
      }
      await cc.refresh();
      setStatus("Updated.");
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  async function setMode(modeNext: ControlMode) {
    const patch: ControlPatch = { controlMode: modeNext };
    if (modeNext === "view_only") patch.paused = true;
    if (modeNext === "assist") patch.paused = false;
    if (modeNext === "auto") patch.paused = false;
    await applyQuick(patch, `Control Center mode → ${modeNext}`);
  }

  const quickToggles = [
    {
      label: mode === "auto" ? "Auto Mode ON" : "Auto Mode OFF",
      body: "Master autonomy switch.",
      active: mode === "auto",
      onPress: () => void setMode(mode === "auto" ? "assist" : "auto"),
    },
    {
      label: snap?.governance.sandboxOnly ? "Practice Mode ON" : "Practice Mode OFF",
      body: "Dry-run / sandbox posture.",
      active: !!snap?.governance.sandboxOnly,
      onPress: () => void applyQuick({ sandboxOnly: !snap?.governance.sandboxOnly }, "Control Center sandbox toggle"),
    },
    {
      label: snap?.portfolio.state === "defensive" ? "Safe Mode ON" : "Safe Mode OFF",
      body: "Defensive clamps + protective presets.",
      active: snap?.portfolio.state === "defensive",
      onPress: () => void applyQuick({ defensiveMode: snap?.portfolio.state !== "defensive" }, "Control Center safe mode toggle"),
    },
    {
      label: snap?.governance.paused ? "Emergency Pause ON" : "Emergency Pause OFF",
      body: "Immediate stop control.",
      active: !!snap?.governance.paused,
      onPress: () => void applyQuick({ paused: !snap?.governance.paused }, "Control Center emergency pause toggle"),
    },
  ];

  return (
    <>
      <Pressable
        onPress={() => setOpen(true)}
        style={{
          position: "absolute",
          right: 18,
          bottom: 86,
          zIndex: 50,
          borderRadius: theme.radii.pill,
          backgroundColor: theme.colors.cyan,
          paddingHorizontal: 16,
          paddingVertical: 12,
          shadowOpacity: 0.25,
          shadowRadius: 12,
          shadowOffset: { width: 0, height: 8 },
          elevation: 8,
        }}
      >
        <Text style={{ color: theme.colors.bg0, fontWeight: "900", letterSpacing: 0.3 }}>Control Center</Text>
      </Pressable>

      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
        <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" }}>
          <Pressable style={{ flex: 1 }} onPress={() => setOpen(false)} />
          <View
            style={{
              maxHeight: "82%",
              backgroundColor: theme.colors.bg1,
              borderTopLeftRadius: 22,
              borderTopRightRadius: 22,
              borderWidth: 1,
              borderColor: theme.colors.border,
              paddingHorizontal: theme.spacing.lg,
              paddingTop: theme.spacing.md,
              paddingBottom: theme.spacing.lg,
            }}
          >
            <View style={{ alignItems: "center", marginBottom: theme.spacing.md }}>
              <View style={{ width: 52, height: 5, borderRadius: 999, backgroundColor: theme.colors.border }} />
            </View>

            <ScrollView showsVerticalScrollIndicator={false}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <View style={{ flex: 1, paddingRight: 12 }}>
                  <Text style={{ color: theme.colors.text, ...theme.typography.title }}>x∆v Control Center</Text>
                  <Text style={{ color: theme.colors.textMuted, marginTop: 4, ...theme.typography.body }}>Sovereign Capital · glanceable controls from any tab</Text>
                </View>
                {snap ? <SystemStateBadge state={snap.portfolio.state} /> : null}
              </View>

              <View style={{ marginTop: theme.spacing.md, flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
                <View style={{ flexGrow: 1, minWidth: 120, padding: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface1, borderWidth: 1, borderColor: theme.colors.border }}>
                  <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Mode</Text>
                  <Text style={{ color: theme.colors.text, marginTop: 6, fontWeight: "900" }}>{formatMode(mode)}</Text>
                </View>
                <View style={{ flexGrow: 1, minWidth: 120, padding: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface1, borderWidth: 1, borderColor: theme.colors.border }}>
                  <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>NAV</Text>
                  <Text style={{ color: theme.colors.text, marginTop: 6, fontWeight: "900" }}>${snap?.portfolio.navUsd.toFixed(2) ?? "0.00"}</Text>
                </View>
                <View style={{ flexGrow: 1, minWidth: 120, padding: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface1, borderWidth: 1, borderColor: theme.colors.border }}>
                  <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>24h</Text>
                  <Text style={{ color: theme.colors.text, marginTop: 6, fontWeight: "900" }}>{snap ? `${snap.portfolio.pct24h >= 0 ? "+" : ""}${snap.portfolio.pct24h.toFixed(2)}%` : "—"}</Text>
                </View>
                <View style={{ flexGrow: 1, minWidth: 120, padding: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface1, borderWidth: 1, borderColor: theme.colors.border }}>
                  <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Drawdown</Text>
                  <Text style={{ color: theme.colors.text, marginTop: 6, fontWeight: "900" }}>{snap ? `${snap.portfolio.drawdownPct.toFixed(2)}%` : "—"}</Text>
                </View>
              </View>

              <View style={{ marginTop: theme.spacing.md, padding: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface1, borderWidth: 1, borderColor: theme.colors.border }}>
                <Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Status</Text>
                <Text style={{ color: theme.colors.text, marginTop: 6, ...theme.typography.body }}>
                  Last update {formatTime(snap?.portfolio.updatedAtMs)} · Source {(snap?.dataSource ?? cc.source).toUpperCase()}
                </Text>
                {snap?.rpcDegraded ? <Text style={{ color: theme.colors.warn, marginTop: 6, ...theme.typography.body }}>RPC degraded warning: execution quality may be reduced.</Text> : null}
                {snap?.pausedReason ? <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>{((mode === "auto") && !snap?.governance.paused) ? "Status detail:" : "Why trading is off:"} {snap.pausedReason}</Text> : null}
              </View>

              <View style={{ marginTop: theme.spacing.md, flexDirection: "row", gap: 10 }}>
                <Pressable
                  onPress={() => void setMode("auto")}
                  style={{
                    flex: 1,
                    paddingVertical: 14,
                    borderRadius: theme.radii.md,
                    backgroundColor: theme.colors.cyan,
                    alignItems: "center",
                  }}
                >
                  <Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>Start AI</Text>
                </Pressable>
                <Pressable
                  onPress={() => void setMode("view_only")}
                  style={{
                    flex: 1,
                    paddingVertical: 14,
                    borderRadius: theme.radii.md,
                    borderWidth: 1,
                    borderColor: theme.colors.danger,
                    backgroundColor: "rgba(251, 113, 133, 0.10)",
                    alignItems: "center",
                  }}
                >
                  <Text style={{ color: theme.colors.danger, fontWeight: "900" }}>Stop AI</Text>
                </Pressable>
              </View>

              <View style={{ marginTop: theme.spacing.md, gap: 10 }}>
                {quickToggles.map((item) => (
                  <Pressable
                    key={item.label}
                    onPress={item.onPress}
                    style={{
                      paddingVertical: 14,
                      paddingHorizontal: 12,
                      borderRadius: theme.radii.md,
                      borderWidth: 1,
                      borderColor: item.active ? theme.colors.cyan : theme.colors.border,
                      backgroundColor: item.active ? theme.colors.surface2 : theme.colors.surface1,
                    }}
                  >
                    <Text style={{ color: item.active ? theme.colors.text : theme.colors.textMuted, fontWeight: "900" }}>{item.label}</Text>
                    <Text style={{ color: theme.colors.textFaint, marginTop: 4, ...theme.typography.body }}>{item.body}</Text>
                  </Pressable>
                ))}
              </View>

              {status ? <Text style={{ color: theme.colors.textMuted, marginTop: theme.spacing.md, ...theme.typography.mono }}>{status}</Text> : null}
            </ScrollView>
          </View>
        </View>
      </Modal>
    </>
  );
}
