import React, { useEffect, useState } from "react";
import { View, Text, Pressable, ScrollView, Switch } from "react-native";
import { useStore } from "../../state/store";
import { BrandHeader } from "../../components/v2/BrandHeader";
import { SurfaceCard } from "../../components/v2/SurfaceCard";
import { useTheme } from "../../utils/useTheme";
import { pageContentContainerStyle, pageShellStyle } from '../../utils/layout';
import { deployInfo, setSettings } from "../../api/client";

export function LoginScreen() {
  const { state, set, session, setSession, unlockOperator, lockOperator } = useStore();
  const theme = useTheme();
  const [status, setStatus] = useState<string>("");

  useEffect(() => {
    (async () => {
      try {
        const info = await deployInfo(state.baseUrl, state.adminKey || undefined);
        const publicMode = Boolean((info as Record<string, unknown>)?.["public_mode"]);
        if (publicMode) {
          try {
            if (state.adminKey) await setSettings(state.baseUrl, { auto_trading: false, dry_run: true }, state.adminKey);
          } catch {
            // ignore
          }
          set({ role: "read_only", adminKey: "", hasAdminKeySecure: false });
          setSession({ locked: false, armed: false });
          setStatus("Public deploy mode detected: switched to read-only.");
          return;
        }
        setStatus("Ready.");
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        setStatus(`Backend check failed · ${msg}`);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const canUnlock = Boolean(state.adminKey || state.hasAdminKeySecure);

  async function handleUnlock() {
    setStatus("Unlocking…");
    const ok = await unlockOperator();
    if (!ok) {
      setStatus(state.biometricsEnabled ? "Unlock failed. Check biometric/device credential permissions." : "Unlock failed. Admin key not available.");
      return;
    }
    setStatus(state.biometricsEnabled ? "Unlocked with biometric/device credential gate." : "Unlocked.");
  }

  async function handleLock() {
    await lockOperator();
    setStatus("Session locked. Admin key cleared from app memory.");
  }

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 24)}>
      <BrandHeader title="x∆v" subtitle="Sovereign Capital · Unlock" rightTag={state.role === "operator" ? "OPERATOR" : "READ"} />

      <SurfaceCard glow="cyan">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Session</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>
          Operator mode requires an explicit unlock each app launch. Trading controls remain disabled until ARMED.
        </Text>

        <View style={{ marginTop: theme.spacing.lg }}>
          <Text style={{ color: theme.colors.textMuted, ...theme.typography.mono }}>Backend</Text>
          <Text style={{ color: theme.colors.text, marginTop: 4, fontFamily: "monospace" }}>{state.baseUrl}</Text>
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <Text style={{ color: theme.colors.textMuted, ...theme.typography.mono }}>Role</Text>
          <Text style={{ color: theme.colors.text, marginTop: 4, fontWeight: "900" }}>{state.role === "operator" ? "Operator" : "Read-only"}</Text>
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <Text style={{ color: theme.colors.textMuted, ...theme.typography.mono }}>Key storage</Text>
          <Text style={{ color: theme.colors.text, marginTop: 4, ...theme.typography.body }}>
            {state.hasAdminKeySecure ? "Secure key present" : "No secure admin key saved"} · Session {session.locked ? "locked" : "unlocked"}
          </Text>
        </View>

        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: theme.spacing.lg }}>
          <View style={{ flex: 1, paddingRight: 12 }}>
            <Text style={{ color: theme.colors.textMuted, ...theme.typography.mono }}>Biometric lock</Text>
            <Text style={{ color: theme.colors.textFaint, marginTop: 2, ...theme.typography.body }}>
              When enabled, the stored operator key requires device biometric or credential unlock on supported devices.
            </Text>
          </View>
          <Switch
            value={state.biometricsEnabled}
            onValueChange={(v) => {
              set({ biometricsEnabled: v });
              setStatus(v ? "Biometric lock enabled. Existing key will be re-saved with authentication the next time you unlock/save." : "Biometric lock disabled.");
            }}
            thumbColor={state.biometricsEnabled ? theme.colors.cyan : theme.colors.border}
          />
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.lg }} />

      <View style={{ flexDirection: "row", gap: 10 }}>
        <Pressable
          onPress={() => set({ onboarded: false, adminKey: "", hasAdminKeySecure: false, role: "read_only" })}
          style={{
            flex: 1,
            paddingVertical: 14,
            borderRadius: theme.radii.md,
            borderWidth: 1,
            borderColor: theme.colors.border,
            backgroundColor: theme.colors.surface1,
            alignItems: "center",
          }}
        >
          <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>Re-Setup</Text>
        </Pressable>

        <Pressable
          disabled={!canUnlock}
          onPress={() => void handleUnlock()}
          style={{
            flex: 1,
            paddingVertical: 14,
            borderRadius: theme.radii.md,
            backgroundColor: canUnlock ? theme.colors.cyan : theme.colors.border,
            alignItems: "center",
          }}
        >
          <Text style={{ color: theme.colors.bg0, fontWeight: "900" }}>{session.locked ? "Unlock" : "Unlocked"}</Text>
        </Pressable>
      </View>

      {state.role === "operator" && !session.locked ? (
        <Pressable
          onPress={() => void handleLock()}
          style={{ marginTop: theme.spacing.md, paddingVertical: 14, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1, alignItems: "center" }}
        >
          <Text style={{ color: theme.colors.textMuted, fontWeight: "900" }}>Lock Now</Text>
        </Pressable>
      ) : null}

      {status ? <Text style={{ color: theme.colors.textMuted, marginTop: theme.spacing.md, ...theme.typography.mono }}>{status}</Text> : null}
    </ScrollView>
  );
}
