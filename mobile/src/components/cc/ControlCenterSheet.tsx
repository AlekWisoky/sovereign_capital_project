import React, { useMemo, useState } from "react";
import { Modal, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { useTheme } from "../../utils/useTheme";
import { useCommandCenter } from "../../commandCenter/useCommandCenter";
import type { ControlMode, ControlPatch } from "../../commandCenter/types";
import { useStore } from "../../state/store";
import { SystemStateBadge } from "./SystemStateBadge";

function formatMode(mode: ControlMode | undefined): string { if (mode === "auto") return "Auto"; if (mode === "assist") return "Assist"; return "View Only"; }
function formatTime(tsMs?: number): string { if (!tsMs) return "—"; try { return new Date(tsMs).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); } catch { return "—"; } }
type PendingMutation = { label: string; patch: ControlPatch; defaultReason: string };

export function ControlCenterSheet() {
  const theme = useTheme();
  const cc = useCommandCenter();
  const { state, session, setSession, unlockOperator } = useStore();
  const snap = cc.snapshot;
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState("");
  const [pending, setPending] = useState<PendingMutation | null>(null);
  const [reason, setReason] = useState("");
  const [armPending, setArmPending] = useState(false);

  const mode = useMemo<ControlMode>(() => (snap?.controlMode ?? snap?.governance.controlMode ?? (snap?.governance.paused ? "view_only" : "assist")) as ControlMode, [snap]);

  function requestMutation(patch: ControlPatch, label: string, defaultReason: string) {
    if (cc.source !== "backend") return void setStatus("Demo mode is read-only. Switch to backend mode before requesting a mutation.");
    if (state.role !== "operator" || session.locked) return void setStatus("Operator unlock required. No control change was sent.");
    if (!session.armed) return void setStatus("Operator session is SAFE. ARM the operator session before requesting a control change.");
    setPending({ patch, label, defaultReason }); setReason(""); setStatus("");
  }

  async function confirmMutation() {
    if (!pending) return;
    const finalReason = reason.trim() || pending.defaultReason;
    setStatus("Applying…");
    try { const res = await cc.setControls(pending.patch, finalReason); if (!res.ok) return void setStatus(res.error ? `Failed · ${res.error}` : "Failed"); await cc.refresh(); setPending(null); setReason(""); setStatus("Updated and reconciled with backend truth."); }
    catch (e: unknown) { setStatus(e instanceof Error ? e.message : String(e)); }
  }

  async function armOperatorSession() {
    if (state.role !== "operator") return void setStatus("Read-only role cannot ARM operator controls.");
    if (session.locked) { const unlocked = await unlockOperator(); if (!unlocked) return void setStatus("Operator unlock failed or was cancelled."); }
    if (!armPending) return setArmPending(true);
    setSession({ armed: true }); setArmPending(false); setStatus("Operator session ARMED locally. Backend authority is unchanged.");
  }

  function requestMode(modeNext: ControlMode) { const patch: ControlPatch = { controlMode: modeNext }; if (modeNext === "view_only") patch.paused = true; if (modeNext === "assist") patch.paused = false; if (modeNext === "auto") patch.paused = false; requestMutation(patch, `Set control mode to ${modeNext}`, `Control Center mode → ${modeNext}`); }

  const quickToggles = [
    { label: mode === "auto" ? "Auto Mode ON" : "Auto Mode OFF", body: "Master autonomy switch. Requires operator ARM + confirmation.", active: mode === "auto", onPress: () => requestMode(mode === "auto" ? "assist" : "auto") },
    { label: snap?.governance.sandboxOnly ? "Practice Mode ON" : "Practice Mode OFF", body: "Dry-run / sandbox posture. Backend remains authoritative.", active: !!snap?.governance.sandboxOnly, onPress: () => requestMutation({ sandboxOnly: !snap?.governance.sandboxOnly }, "Change Practice Mode", "Control Center sandbox change") },
    { label: snap?.portfolio.state === "defensive" ? "Safe Mode ON" : "Safe Mode OFF", body: "Defensive clamps + protective presets.", active: snap?.portfolio.state === "defensive", onPress: () => requestMutation({ defensiveMode: snap?.portfolio.state !== "defensive" }, "Change Safe Mode", "Control Center safe mode change") },
    { label: snap?.governance.paused ? "Emergency Pause ON" : "Emergency Pause OFF", body: "Immediate stop control. Reconciliation follows the backend response.", active: !!snap?.governance.paused, onPress: () => requestMutation({ paused: !snap?.governance.paused }, "Change Emergency Pause", "Control Center emergency pause change") },
  ];

  return <>
    <Pressable onPress={() => setOpen(true)} style={{ position: "absolute", right: 18, bottom: 86, zIndex: 50, borderRadius: theme.radii.pill, backgroundColor: theme.colors.cyan, paddingHorizontal: 16, paddingVertical: 12, shadowOpacity: 0.25, shadowRadius: 12, shadowOffset: { width: 0, height: 8 }, elevation: 8 }}><Text style={{ color: theme.colors.bg0, fontWeight: "900", letterSpacing: 0.3 }}>Control Center</Text></Pressable>
    <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
      <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" }}><Pressable style={{ flex: 1 }} onPress={() => setOpen(false)} />
        <View style={{ maxHeight: "86%", backgroundColor: theme.colors.bg1, borderTopLeftRadius: 22, borderTopRightRadius: 22, borderWidth: 1, borderColor: theme.colors.border, paddingHorizontal: theme.spacing.lg, paddingTop: theme.spacing.md, paddingBottom: theme.spacing.lg }}>
          <ScrollView showsVerticalScrollIndicator={false}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}><View style={{ flex: 1, paddingRight: 12 }}><Text style={{ color: theme.colors.text, ...theme.typography.title }}>x∆v Control Center</Text><Text style={{ color: theme.colors.textMuted, marginTop: 4, ...theme.typography.body }}>Read canonical state; request guarded mutations.</Text></View>{snap ? <SystemStateBadge state={snap.portfolio.state} /> : null}</View>
            <View style={{ marginTop: theme.spacing.md, flexDirection: "row", flexWrap: "wrap", gap: 10 }}><View style={{ flexGrow: 1, minWidth: 120, padding: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface1, borderWidth: 1, borderColor: theme.colors.border }}><Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Mode</Text><Text style={{ color: theme.colors.text, marginTop: 6, fontWeight: "900" }}>{formatMode(mode)}</Text></View><View style={{ flexGrow: 1, minWidth: 120, padding: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface1, borderWidth: 1, borderColor: theme.colors.border }}><Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>NAV</Text><Text style={{ color: theme.colors.text, marginTop: 6, fontWeight: "900" }}>${snap?.portfolio.navUsd.toFixed(2) ?? "0.00"}</Text></View><View style={{ flexGrow: 1, minWidth: 120, padding: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface1, borderWidth: 1, borderColor: theme.colors.border }}><Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>24h</Text><Text style={{ color: theme.colors.text, marginTop: 6, fontWeight: "900" }}>{snap ? `${snap.portfolio.pct24h >= 0 ? "+" : ""}${snap.portfolio.pct24h.toFixed(2)}%` : "—"}</Text></View><View style={{ flexGrow: 1, minWidth: 120, padding: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface1, borderWidth: 1, borderColor: theme.colors.border }}><Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Drawdown</Text><Text style={{ color: theme.colors.text, marginTop: 6, fontWeight: "900" }}>{snap ? `${snap.portfolio.drawdownPct.toFixed(2)}%` : "—"}</Text></View></View>
            <View style={{ marginTop: theme.spacing.md, padding: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface1, borderWidth: 1, borderColor: theme.colors.border }}><Text style={{ color: theme.colors.textFaint, ...theme.typography.mono }}>Operator state</Text><Text style={{ color: theme.colors.text, marginTop: 6, ...theme.typography.body }}>Role {state.role} · {session.locked ? "LOCKED" : session.armed ? "ARMED" : "SAFE"} · Source {(snap?.dataSource ?? cc.source).toUpperCase()}</Text>{snap?.rpcDegraded ? <Text style={{ color: theme.colors.warn, marginTop: 6, ...theme.typography.body }}>RPC degraded warning: execution quality may be reduced.</Text> : null}{snap?.pausedReason ? <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>{snap.pausedReason}</Text> : null}</View>
            <Pressable onPress={() => void armOperatorSession()} style={{ marginTop: theme.spacing.md, paddingVertical: 13, borderRadius: theme.radii.md, borderWidth: 1, borderColor: session.armed ? theme.colors.good : theme.colors.warn, backgroundColor: theme.colors.surface1, alignItems: "center" }}><Text style={{ color: session.armed ? theme.colors.good : theme.colors.warn, fontWeight: "900" }}>{session.armed ? "Operator session ARMED" : armPending ? "Confirm ARM operator session" : "ARM operator session"}</Text><Text style={{ color: theme.colors.textFaint, marginTop: 4 }}>{session.armed ? "Local safety state; backend authority is unchanged." : "Two-step local safety gate; this does not grant backend execution authority."}</Text></Pressable>
            <View style={{ marginTop: theme.spacing.md, padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}><Text style={{ color: theme.colors.text, fontWeight: "900" }}>Mutation guard</Text><Text style={{ color: theme.colors.textMuted, marginTop: 5 }}>Every control mutation requires backend mode, operator unlock, ARM state, explicit confirmation, and a reason. Backend capability remains authoritative.</Text></View>
            <View style={{ marginTop: theme.spacing.md, gap: 10 }}>{quickToggles.map((item) => <Pressable key={item.label} onPress={item.onPress} style={{ paddingVertical: 14, paddingHorizontal: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: item.active ? theme.colors.cyan : theme.colors.border, backgroundColor: item.active ? theme.colors.surface2 : theme.colors.surface1 }}><Text style={{ color: item.active ? theme.colors.text : theme.colors.textMuted, fontWeight: "900" }}>{item.label}</Text><Text style={{ color: theme.colors.textFaint, marginTop: 4, ...theme.typography.body }}>{item.body}</Text></Pressable>)}</View>
            {pending ? <View style={{ marginTop: theme.spacing.md, padding: 14, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.warn, backgroundColor: theme.colors.surface1 }}><Text style={{ color: theme.colors.warn, fontWeight: "900" }}>Confirm: {pending.label}</Text><Text style={{ color: theme.colors.textMuted, marginTop: 6 }}>This sends a capability-checked backend mutation. No local toggle is treated as authoritative.</Text><TextInput value={reason} onChangeText={setReason} placeholder="Reason (optional; default reason will be recorded)" placeholderTextColor={theme.colors.textFaint} style={{ marginTop: 10, padding: 11, borderWidth: 1, borderColor: theme.colors.border, borderRadius: theme.radii.md, color: theme.colors.text, backgroundColor: theme.colors.bg1 }} /><View style={{ flexDirection: "row", gap: 10, marginTop: 10 }}><Pressable onPress={() => setPending(null)} style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, alignItems: "center" }}><Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>Cancel</Text></Pressable><Pressable onPress={() => void confirmMutation()} style={{ flex: 1, paddingVertical: 12, borderRadius: theme.radii.md, backgroundColor: theme.colors.warn, alignItems: "center" }}><Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>Confirm mutation</Text></Pressable></View></View> : null}
            {status ? <Text style={{ color: theme.colors.textMuted, marginTop: theme.spacing.md, ...theme.typography.mono }}>{status}</Text> : null}<Text style={{ color: theme.colors.textFaint, marginTop: theme.spacing.md, ...theme.typography.mono }}>Last update {formatTime(snap?.portfolio.updatedAtMs)}</Text>
          </ScrollView>
        </View>
      </View>
    </Modal>
  </>;
}
