import React, { useEffect, useMemo, useState } from 'react';
import { View, Text, TextInput, Pressable, ScrollView, Switch } from 'react-native';
import { useStore } from '../../state/store';
import { BrandHeader } from '../../components/v2/BrandHeader';
import { SurfaceCard } from '../../components/v2/SurfaceCard';
import { LiveModeBanner } from '../../components/cc/LiveModeBanner';
import { SegmentedTabs } from '../../components/v2/SegmentedTabs';
import { getTheme, type ThemeName } from '../../utils/theme';
import { useTheme } from '../../utils/useTheme';
import { pageContentContainerStyle, pageShellStyle } from '../../utils/layout';
import { health, deployInfo, rpcPreferences, saveRpcPreferences, launchState, setLaunchMode, listPresets, applyPreset } from '../../api/client';

const LAUNCH_MODES = ['V1_ONLY', 'V1_PLUS_STABLE_ALPHA', 'STAGED_MULTI_STRATEGY', 'FULL_MULTI_STRATEGY'] as const;
const ROLES = ['read_only', 'operator'] as const;
const THEMES = ['cyan_ledger', 'violet_pulse', 'matrix_emerald'] as const;
const GAS = ['standard', 'fast', 'instant'] as const;
const SEND = ['public', 'private', 'protected_rpc'] as const;
const BRAIN = ['off', 'shadow', 'suggest', 'auto'] as const;
const DATA_SOURCE = ['backend', 'mock'] as const;
const RISK = ['conservative', 'moderate', 'aggressive'] as const;

type Role = typeof ROLES[number];

function sanitizeUrl(value: string): string {
  return value.trim().replace(/\/$/, '');
}

function boolLabel(value: boolean, enabled: string, disabled: string): string {
  return value ? enabled : disabled;
}

function parseList(text: string): string[] {
  return text.split(/\n|,/).map((x) => x.trim()).filter(Boolean);
}

function FieldLabel({ title, subtitle }: { title: string; subtitle?: string }) {
  const theme = useTheme();
  return (
    <View style={{ marginBottom: 8 }}>
      <Text style={{ color: theme.colors.textMuted, fontSize: 12, fontWeight: '800', letterSpacing: 0.4 }}>{title}</Text>
      {subtitle ? <Text style={{ color: theme.colors.textFaint, marginTop: 4, fontSize: 12 }}>{subtitle}</Text> : null}
    </View>
  );
}

function Input(props: { value: string; onChangeText: (v: string) => void; placeholder?: string; multiline?: boolean; secureTextEntry?: boolean; keyboardType?: 'default' | 'numeric' | 'url'; }) {
  const theme = useTheme();
  return (
    <TextInput
      value={props.value}
      onChangeText={props.onChangeText}
      placeholder={props.placeholder}
      placeholderTextColor={theme.colors.textFaint}
      autoCapitalize="none"
      autoCorrect={false}
      multiline={props.multiline}
      secureTextEntry={props.secureTextEntry}
      keyboardType={props.keyboardType}
      style={{
        marginTop: 2,
        minHeight: props.multiline ? 72 : 48,
        paddingHorizontal: 12,
        paddingVertical: props.multiline ? 12 : 10,
        borderRadius: theme.radii.md,
        borderWidth: 1,
        borderColor: theme.colors.border,
        color: theme.colors.text,
        backgroundColor: theme.colors.surface1,
        fontFamily: 'monospace',
        textAlignVertical: props.multiline ? 'top' : 'center',
      }}
    />
  );
}

function ToggleLine({ title, subtitle, value, onValueChange }: { title: string; subtitle: string; value: boolean; onValueChange: (v: boolean) => void }) {
  const theme = useTheme();
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, paddingVertical: 10 }}>
      <View style={{ flex: 1 }}>
        <Text style={{ color: theme.colors.text, fontWeight: '800' }}>{title}</Text>
        <Text style={{ color: theme.colors.textFaint, marginTop: 4, fontSize: 12 }}>{subtitle}</Text>
      </View>
      <Switch value={value} onValueChange={onValueChange} thumbColor={value ? theme.colors.cyan : theme.colors.border} trackColor={{ false: theme.colors.surface2, true: theme.glow.cyan }} />
    </View>
  );
}

export function SetupScreen() {
  const theme = useTheme();
  const { state, set, multichain, refreshMultichain, selectActiveChain } = useStore();

  const [baseUrl, setBaseUrl] = useState(state.baseUrl);
  const [adminKey, setAdminKey] = useState(state.adminKey);
  const [role, setRole] = useState<Role>(state.role);
  const [themeName, setThemeName] = useState<ThemeName>(state.themeName);
  const [status, setStatus] = useState('');
  const [premiumRead, setPremiumRead] = useState((state.premiumRpcReadUrls ?? []).join('\n'));
  const [premiumSend, setPremiumSend] = useState((state.premiumRpcSendUrls ?? []).join('\n'));
  const [premiumPrivate, setPremiumPrivate] = useState((state.premiumRpcPrivateUrls ?? []).join('\n'));
  const [launchModeLocal, setLaunchModeLocal] = useState<typeof LAUNCH_MODES[number]>(state.preferredLaunchMode ?? 'V1_ONLY');
  const [launchInfo, setLaunchInfo] = useState<any>(null);
  const [presetList, setPresetList] = useState<string[]>([]);
  const [chain, setChainLocal] = useState(state.activeChain ?? state.chain ?? 'ethereum');
  const [preset, setPresetLocal] = useState(state.preset || 'default');
  const [autoTrading, setAutoTrading] = useState(state.autoTrading);
  const [gasMode, setGasMode] = useState<typeof GAS[number]>(state.gasMode);
  const [sendMode, setSendMode] = useState<typeof SEND[number]>(state.sendMode);
  const [autoReinvestEnabled, setAutoReinvestEnabled] = useState(state.autoReinvestEnabled);
  const [reinvestRate, setReinvestRate] = useState(String(state.reinvestRate));
  const [minProfitAbs, setMinProfitAbs] = useState(state.minProfitAbs);
  const [minProfitBps, setMinProfitBps] = useState(String(state.minProfitBps));
  const [slippageBps, setSlippageBps] = useState(String(state.slippageBps));
  const [requireSimulation, setRequireSimulation] = useState(state.requireSimulation);
  const [antiFrontrun, setAntiFrontrun] = useState(state.antiFrontrun);
  const [brainMode, setBrainMode] = useState<typeof BRAIN[number]>(state.brainMode);
  const [walletAddressesText, setWalletAddressesText] = useState((state.walletAddresses ?? []).join('\n'));
  const [defaultWithdrawalDest, setDefaultWithdrawalDest] = useState(state.defaultWithdrawalDest);
  const [unitTokenAddress, setUnitTokenAddress] = useState(state.unitTokenAddress);
  const [baseBorrowAmount, setBaseBorrowAmount] = useState(state.baseBorrowAmount);
  const [maxBorrowAmount, setMaxBorrowAmount] = useState(state.maxBorrowAmount);
  const [ccDataSource, setCcDataSource] = useState<typeof DATA_SOURCE[number]>(state.ccDataSource ?? 'mock');
  const [ccRefreshMs, setCcRefreshMs] = useState(String(state.ccRefreshMs ?? 4500));
  const [biometricsEnabled, setBiometricsEnabled] = useState(state.biometricsEnabled);
  const [riskTolerance, setRiskTolerance] = useState<typeof RISK[number]>('moderate');

  const safeBaseUrl = useMemo(() => sanitizeUrl(baseUrl), [baseUrl]);
  const isOperator = role === 'operator';
  const recentUrls = useMemo(() => {
    const seen = new Set<string>();
    return [safeBaseUrl, ...(state.backendUrls ?? [])].filter((x) => {
      const url = String(x || '').trim();
      if (!url || seen.has(url)) return false;
      seen.add(url);
      return true;
    });
  }, [safeBaseUrl, state.backendUrls]);

  useEffect(() => {
    let alive = true;
    async function boot() {
      if (!safeBaseUrl) return;
      try {
        await refreshMultichain();
      } catch {
        // keep local chain
      }
      try {
        const info = await launchState(safeBaseUrl, isOperator ? adminKey.trim() : undefined);
        if (!alive) return;
        if ((info as any)?.profile?.mode) setLaunchModeLocal(String((info as any).profile.mode) as typeof LAUNCH_MODES[number]);
        setLaunchInfo(info);
      } catch {
        if (!alive) return;
        setLaunchInfo(null);
      }
      try {
        const prefs = await listPresets(safeBaseUrl, isOperator ? adminKey.trim() : undefined);
        if (!alive) return;
        const items = Array.isArray((prefs as any)?.items) ? (prefs as any).items : Array.isArray((prefs as any)?.presets) ? (prefs as any).presets : [];
        const names = items.map((item: any) => typeof item === 'string' ? item : String(item?.name ?? item?.preset ?? '')).filter(Boolean);
        setPresetList(names.length ? names : ['default']);
      } catch {
        if (!alive) return;
        setPresetList(['default']);
      }
      if (!isOperator || !adminKey.trim()) return;
      try {
        const prefs = await rpcPreferences(safeBaseUrl, adminKey.trim());
        if (!alive) return;
        const read = Array.isArray((prefs as Record<string, unknown>)?.read) ? ((prefs as Record<string, unknown>).read as string[]) : [];
        const send = Array.isArray((prefs as Record<string, unknown>)?.send) ? ((prefs as Record<string, unknown>).send as string[]) : [];
        const priv = Array.isArray((prefs as Record<string, unknown>)?.private) ? ((prefs as Record<string, unknown>).private as string[]) : [];
        if (!premiumRead.trim() && read.length) setPremiumRead(read.join('\n'));
        if (!premiumSend.trim() && send.length) setPremiumSend(send.join('\n'));
        if (!premiumPrivate.trim() && priv.length) setPremiumPrivate(priv.join('\n'));
      } catch {
        // keep local fields
      }
    }
    void boot();
    return () => { alive = false; };
  }, [safeBaseUrl, isOperator, adminKey, refreshMultichain]);

  async function testConnection() {
    setStatus('Testing backend…');
    try {
      const h = await health(safeBaseUrl, isOperator ? adminKey.trim() : undefined);
      const info = await deployInfo(safeBaseUrl, isOperator ? adminKey.trim() : undefined);
      const mode = Boolean((info as Record<string, unknown>)?.public_mode) ? 'public_mode' : 'private_mode';
      setStatus(`Connected · health=${String((h as any)?.ok ?? true)} · ${mode}`);
    } catch (e: unknown) {
      setStatus(e instanceof Error ? `Failed · ${e.message}` : `Failed · ${String(e)}`);
    }
  }

  async function save() {
    const url = safeBaseUrl;
    const key = adminKey.trim();
    const backendUrls = [url, ...(state.backendUrls ?? [])].map((x) => String(x || '').trim()).filter(Boolean).filter((x, i, arr) => arr.indexOf(x) === i).slice(0, 8);
    const readUrls = parseList(premiumRead).slice(0, 8);
    const sendUrls = parseList(premiumSend).slice(0, 8);
    const privateUrls = parseList(premiumPrivate).slice(0, 8);
    const walletAddresses = parseList(walletAddressesText).slice(0, 12);
    set({
      onboarded: true,
      baseUrl: url,
      backendUrls,
      premiumRpcReadUrls: readUrls,
      premiumRpcSendUrls: sendUrls,
      premiumRpcPrivateUrls: privateUrls,
      preferredLaunchMode: launchModeLocal,
      adminKey: isOperator ? key : '',
      hasAdminKeySecure: isOperator ? Boolean(key) : false,
      role,
      themeName,
      biometricsEnabled,
      chain,
      activeChain: chain,
      preset,
      autoTrading,
      gasMode,
      sendMode,
      autoReinvestEnabled,
      reinvestRate: Number(reinvestRate) || 0,
      minProfitAbs,
      minProfitBps: Number(minProfitBps) || 0,
      slippageBps: Number(slippageBps) || 0,
      requireSimulation,
      antiFrontrun,
      brainMode,
      walletAddresses,
      defaultWithdrawalDest,
      unitTokenAddress,
      baseBorrowAmount,
      maxBorrowAmount,
      ccDataSource,
      ccRefreshMs: Math.max(1500, Number(ccRefreshMs) || 4500),
    });
    setStatus('Saved locally. Synchronizing backend…');
    if (url && chain) {
      try {
        await selectActiveChain(chain);
      } catch {
        // local state already updated
      }
    }
    if (isOperator && key && url) {
      try {
        await saveRpcPreferences(url, { read: readUrls, send: sendUrls, private: privateUrls }, key);
        await setLaunchMode(url, launchModeLocal, key);
        if (preset) {
          try {
            await applyPreset(url, chain, preset, key);
          } catch {
            // preset may be missing on some backends
          }
        }
        setStatus('Saved and synchronized.');
      } catch (e: unknown) {
        setStatus(e instanceof Error ? `Saved locally · backend sync pending · ${e.message}` : `Saved locally · backend sync pending · ${String(e)}`);
      }
      return;
    }
    setStatus('Saved.');
  }

  return (
    <ScrollView style={pageShellStyle(theme)} contentContainerStyle={pageContentContainerStyle(theme, 36)}>
      <BrandHeader title="x∆v" subtitle="Sovereign Capital · Installable operator setup" />

      <LiveModeBanner mode={ccDataSource === 'backend' ? 'backend-mock' : 'demo'} sourceLabel={safeBaseUrl || 'Not configured'} note="Choose backend mode for live governance and execution visibility. Demo/mock mode keeps the app deterministic for walkthroughs and UI validation." />

      <View style={{ height: theme.spacing.lg }} />
      <SurfaceCard glow="violet">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Backend + Identity</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>This app is an operator-first command surface. The backend remains the source of truth for execution, capital, and governance state.</Text>

        <View style={{ marginTop: theme.spacing.md }}>
          <FieldLabel title="Backend base URL" subtitle="Primary VPS or tunnel URL for the x∆v backend." />
          <Input value={baseUrl} onChangeText={setBaseUrl} placeholder="https://your-vps.example" keyboardType="url" />
        </View>

        {recentUrls.length ? (
          <View style={{ marginTop: theme.spacing.md }}>
            <FieldLabel title="Saved backends" />
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
              {recentUrls.map((url) => (
                <Pressable key={url} onPress={() => setBaseUrl(url)} style={{ paddingVertical: 8, paddingHorizontal: 10, borderRadius: theme.radii.pill, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
                  <Text style={{ color: theme.colors.textMuted, fontSize: 12, fontWeight: '800' }}>{url}</Text>
                </Pressable>
              ))}
            </View>
          </View>
        ) : null}

        <View style={{ marginTop: theme.spacing.md }}>
          <FieldLabel title="Role" subtitle="Operator can mutate state. Read-only shows the same context, but controls stay locked." />
          <SegmentedTabs options={ROLES} value={role} onChange={setRole} />
        </View>

        {isOperator ? (
          <View style={{ marginTop: theme.spacing.md }}>
            <FieldLabel title="Admin key" subtitle="Stored securely. Never persisted in AsyncStorage." />
            <Input value={adminKey} onChangeText={setAdminKey} placeholder="operator admin key" secureTextEntry />
          </View>
        ) : null}

        <View style={{ marginTop: theme.spacing.sm }}>
          <ToggleLine title="Biometric unlock" subtitle="Require device authentication when unlocking operator control." value={biometricsEnabled} onValueChange={setBiometricsEnabled} />
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.lg }} />
      <SurfaceCard glow="cyan">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Launch + Multi-Chain</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>V1-first rollout remains the safety baseline. Use launch mode and readiness data to expand only when the backend says the family is ready.</Text>

        <View style={{ marginTop: theme.spacing.md }}>
          <FieldLabel title="Preferred launch mode" subtitle="Persisted locally and synchronized to backend when operator credentials are available." />
          <View style={{ gap: 10 }}>
            {LAUNCH_MODES.map((mode) => {
              const active = launchModeLocal === mode;
              return (
                <Pressable key={mode} onPress={() => setLaunchModeLocal(mode)} style={{ paddingVertical: 12, paddingHorizontal: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: active ? theme.colors.cyan : theme.colors.border, backgroundColor: active ? theme.colors.surface2 : theme.colors.surface1 }}>
                  <Text style={{ color: active ? theme.colors.text : theme.colors.textMuted, fontWeight: '900' }}>{mode.replace(/_/g, ' ')}</Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        {launchInfo?.recommended_next_family ? (
          <View style={{ marginTop: theme.spacing.md, padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1 }}>
            <Text style={{ color: theme.colors.text, fontWeight: '900' }}>Recommended next family</Text>
            <Text style={{ color: theme.colors.cyan, fontWeight: '900', marginTop: 4 }}>{String(launchInfo.recommended_next_family).replace(/_/g, ' ')}</Text>
            <Text style={{ color: theme.colors.textFaint, marginTop: 6 }}>{Array.isArray(launchInfo.reasons) ? launchInfo.reasons.join(' · ') : 'Awaiting launch summary.'}</Text>
          </View>
        ) : null}

        <View style={{ marginTop: theme.spacing.md }}>
          <FieldLabel title="Active chain" subtitle="Matches the backend multichain controller when available." />
          <SegmentedTabs options={((multichain.chains?.length ? multichain.chains : [chain]) as readonly string[])} value={chain} onChange={(next) => setChainLocal(next)} />
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <FieldLabel title="Preset" subtitle="Backend preset bundle to apply for live/runtime defaults." />
          <SegmentedTabs options={((presetList.length ? presetList : ['default']) as readonly string[])} value={preset} onChange={(next) => setPresetLocal(next)} />
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.lg }} />
      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Execution Profile</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>Set the mobile-side operator profile that mirrors backend trading posture, gas behavior, routing preference, and simulation policy.</Text>

        <View style={{ marginTop: theme.spacing.md }}>
          <FieldLabel title="Trading posture" />
          <ToggleLine title="Auto trading" subtitle={boolLabel(autoTrading, 'Mobile profile favors active autonomy.', 'Mobile profile favors supervised / disabled autonomy.')} value={autoTrading} onValueChange={setAutoTrading} />
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <FieldLabel title="Gas mode" />
          <SegmentedTabs options={GAS} value={gasMode} onChange={setGasMode} />
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <FieldLabel title="Send mode" subtitle="Public, private, or protected RPC preference for human/operator posture." />
          <SegmentedTabs options={SEND} value={sendMode} onChange={setSendMode} />
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <FieldLabel title="Brain mode" subtitle="Off/shadow/suggest/auto is a mobile preference; backend remains authoritative." />
          <SegmentedTabs options={BRAIN} value={brainMode} onChange={setBrainMode} />
        </View>

        <ToggleLine title="Require simulation" subtitle="Do not send operator-triggered actions without a simulation requirement in posture." value={requireSimulation} onValueChange={setRequireSimulation} />
        <ToggleLine title="Anti-frontrun" subtitle="Preserve protected route posture and operator awareness around competition-sensitive flows." value={antiFrontrun} onValueChange={setAntiFrontrun} />
        <ToggleLine title="Auto reinvest" subtitle="Reflects the operator preference for treasury growth posture." value={autoReinvestEnabled} onValueChange={setAutoReinvestEnabled} />

        <View style={{ flexDirection: 'row', gap: 10, marginTop: theme.spacing.md }}>
          <View style={{ flex: 1 }}>
            <FieldLabel title="Reinvest rate %" />
            <Input value={reinvestRate} onChangeText={setReinvestRate} keyboardType="numeric" />
          </View>
          <View style={{ flex: 1 }}>
            <FieldLabel title="Min profit abs" />
            <Input value={minProfitAbs} onChangeText={setMinProfitAbs} keyboardType="numeric" />
          </View>
        </View>

        <View style={{ flexDirection: 'row', gap: 10, marginTop: theme.spacing.md }}>
          <View style={{ flex: 1 }}>
            <FieldLabel title="Min profit bps" />
            <Input value={minProfitBps} onChangeText={setMinProfitBps} keyboardType="numeric" />
          </View>
          <View style={{ flex: 1 }}>
            <FieldLabel title="Slippage bps" />
            <Input value={slippageBps} onChangeText={setSlippageBps} keyboardType="numeric" />
          </View>
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.lg }} />
      <SurfaceCard glow="violet">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Capital + Treasury</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>These fields configure the human-facing treasury profile: wallet destinations, unit token, borrow sizing, and refresh/data-source preferences.</Text>

        <View style={{ flexDirection: 'row', gap: 10, marginTop: theme.spacing.md }}>
          <View style={{ flex: 1 }}>
            <FieldLabel title="Base borrow amount" />
            <Input value={baseBorrowAmount} onChangeText={setBaseBorrowAmount} keyboardType="numeric" />
          </View>
          <View style={{ flex: 1 }}>
            <FieldLabel title="Max borrow amount" />
            <Input value={maxBorrowAmount} onChangeText={setMaxBorrowAmount} keyboardType="numeric" />
          </View>
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <FieldLabel title="Wallet addresses" subtitle="Saved recipient or treasury addresses, one per line." />
          <Input value={walletAddressesText} onChangeText={setWalletAddressesText} multiline placeholder="0x...\n0x..." />
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <FieldLabel title="Default withdrawal destination" />
          <Input value={defaultWithdrawalDest} onChangeText={setDefaultWithdrawalDest} placeholder="0x..." />
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <FieldLabel title="Unit token address" />
          <Input value={unitTokenAddress} onChangeText={setUnitTokenAddress} placeholder="0x..." />
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <FieldLabel title="Command center data source" subtitle="Backend uses live contract APIs. Mock keeps the operator UI deterministic when backend is unavailable." />
          <SegmentedTabs options={DATA_SOURCE} value={ccDataSource} onChange={setCcDataSource} />
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <FieldLabel title="Refresh interval ms" />
          <Input value={ccRefreshMs} onChangeText={setCcRefreshMs} keyboardType="numeric" />
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.lg }} />
      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Theme + Operator View</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>Choose a visual language that still reads like a sovereign operations console rather than a retail dashboard.</Text>

        <View style={{ flexDirection: 'row', gap: 10, marginTop: theme.spacing.md, flexWrap: 'wrap' }}>
          {THEMES.map((name) => {
            const active = themeName === name;
            const preview = getTheme(name);
            return (
              <Pressable key={name} onPress={() => setThemeName(name)} style={{ flexBasis: '31%', flexGrow: 1, padding: 12, borderRadius: theme.radii.md, borderWidth: 1, borderColor: active ? preview.colors.cyan : theme.colors.border, backgroundColor: preview.colors.surface0 }}>
                <Text style={{ color: preview.colors.text, fontWeight: '900' }}>{name.replace(/_/g, ' ')}</Text>
                <Text style={{ color: preview.colors.textMuted, fontSize: 12, marginTop: 4 }}>accent {preview.colors.cyan}</Text>
              </Pressable>
            );
          })}
        </View>

        <View style={{ marginTop: theme.spacing.md }}>
          <FieldLabel title="Operator risk framing" subtitle="Used only as a local preference for guidance copy in the current mobile layer." />
          <SegmentedTabs options={RISK} value={riskTolerance} onChange={setRiskTolerance} />
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.lg }} />
      <SurfaceCard glow="none">
        <Text style={{ color: theme.colors.text, ...theme.typography.h1 }}>Premium Routing Endpoints</Text>
        <Text style={{ color: theme.colors.textMuted, marginTop: 6, ...theme.typography.body }}>Optional premium read, send, and private RPC lists. Stored for backend preference wiring and operator governance, never to bypass safety controls.</Text>

        <View style={{ marginTop: theme.spacing.md }}>
          <FieldLabel title="Premium read RPCs" />
          <Input value={premiumRead} onChangeText={setPremiumRead} multiline placeholder="https://read-rpc-1" />
        </View>
        <View style={{ marginTop: theme.spacing.md }}>
          <FieldLabel title="Premium send RPCs" />
          <Input value={premiumSend} onChangeText={setPremiumSend} multiline placeholder="https://send-rpc-1" />
        </View>
        <View style={{ marginTop: theme.spacing.md }}>
          <FieldLabel title="Premium private / bundle RPCs" />
          <Input value={premiumPrivate} onChangeText={setPremiumPrivate} multiline placeholder="https://private-rpc-1" />
        </View>
      </SurfaceCard>

      <View style={{ height: theme.spacing.lg }} />
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <Pressable onPress={() => void testConnection()} style={{ flex: 1, paddingVertical: 14, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface1, alignItems: 'center' }}>
          <Text style={{ color: theme.colors.textMuted, fontWeight: '900' }}>Test</Text>
        </Pressable>
        <Pressable onPress={() => void save()} style={{ flex: 1, paddingVertical: 14, borderRadius: theme.radii.md, backgroundColor: theme.colors.cyan, alignItems: 'center' }}>
          <Text style={{ color: theme.colors.bg0, fontWeight: '900' }}>Save Setup</Text>
        </Pressable>
      </View>

      {status ? <Text style={{ color: theme.colors.textMuted, marginTop: theme.spacing.md, fontSize: 12, fontFamily: 'monospace' }}>{status}</Text> : null}
    </ScrollView>
  );
}
