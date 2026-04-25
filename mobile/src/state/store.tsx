import AsyncStorage from '@react-native-async-storage/async-storage';
import React, { createContext, useContext, useEffect, useMemo, useReducer } from 'react';
import { fetchChains, selectChain } from '../api/client';
import { ENV } from '../config/env';
import { deleteSecureString, getSecureString, setSecureString } from '../utils/secureStore';
import type { ThemeName } from '../utils/theme';

export type Role = 'operator' | 'read_only';

export type AppSettings = {
  onboarded: boolean;
  baseUrl: string;
  backendUrls: string[];
  premiumRpcReadUrls: string[];
  premiumRpcSendUrls: string[];
  premiumRpcPrivateUrls: string[];
  preferredLaunchMode: 'V1_ONLY' | 'V1_PLUS_STABLE_ALPHA' | 'STAGED_MULTI_STRATEGY' | 'FULL_MULTI_STRATEGY';
  adminKey: string;
  hasAdminKeySecure: boolean;
  role: Role;
  themeName: ThemeName;
  biometricsEnabled: boolean;
  chain: string;
  preset: string;
  autoTrading: boolean;
  gasMode: 'standard' | 'fast' | 'instant';
  sendMode: 'public' | 'private' | 'protected_rpc';
  autoReinvestEnabled: boolean;
  reinvestRate: number;
  minProfitAbs: string;
  minProfitBps: number;
  slippageBps: number;
  requireSimulation: boolean;
  antiFrontrun: boolean;
  brainMode: 'off' | 'shadow' | 'suggest' | 'auto';
  walletAddresses: string[];
  defaultWithdrawalDest: string;
  unitTokenAddress: string;
  baseBorrowAmount: string;
  maxBorrowAmount: string;
  activeChain?: string;
  ccDataSource?: 'backend' | 'mock';
  ccRefreshMs?: number;
};

const INITIAL_BACKENDS = ENV.defaultBackendUrl ? [ENV.defaultBackendUrl] : [];

const DEFAULTS: AppSettings = {
  onboarded: false,
  baseUrl: ENV.defaultBackendUrl,
  backendUrls: INITIAL_BACKENDS,
  premiumRpcReadUrls: [],
  premiumRpcSendUrls: [],
  premiumRpcPrivateUrls: [],
  preferredLaunchMode: 'V1_ONLY',
  adminKey: '',
  hasAdminKeySecure: false,
  role: 'read_only',
  themeName: 'cyan_ledger',
  biometricsEnabled: false,
  chain: ENV.defaultChain,
  preset: 'default',
  autoTrading: false,
  gasMode: 'standard',
  sendMode: 'public',
  autoReinvestEnabled: false,
  reinvestRate: 0,
  minProfitAbs: '0',
  minProfitBps: 0,
  slippageBps: 50,
  requireSimulation: false,
  antiFrontrun: false,
  brainMode: 'off',
  activeChain: undefined,
  walletAddresses: [],
  defaultWithdrawalDest: '',
  unitTokenAddress: '',
  baseBorrowAmount: '0',
  maxBorrowAmount: '0',
  ccDataSource: 'mock',
  ccRefreshMs: 4500,
};

type Action = { type: 'set'; patch: Partial<AppSettings> } | { type: 'reset' };

function reducer(state: AppSettings, action: Action): AppSettings {
  if (action.type === 'reset') return { ...DEFAULTS };
  if (action.type === 'set') return { ...state, ...action.patch };
  return state;
}

type MultiChainInfo = { ok: boolean; active: string; chains: string[]; last_refresh_ms: number };

export type SessionState = {
  locked: boolean;
  armed: boolean;
};

const Ctx = createContext<{
  state: AppSettings;
  set: (patch: Partial<AppSettings>) => void;
  reset: () => void;
  session: SessionState;
  setSession: (patch: Partial<SessionState>) => void;
  unlockOperator: () => Promise<boolean>;
  lockOperator: () => Promise<void>;
  multichain: MultiChainInfo;
  refreshMultichain: () => Promise<void>;
  selectActiveChain: (chain: string) => Promise<void>;
  hydrated: boolean;
} | null>(null);

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, DEFAULTS);
  const [multichain, setMultichain] = React.useState<MultiChainInfo>({ ok: true, active: '', chains: [], last_refresh_ms: 0 });
  const [session, setSessionState] = React.useState<SessionState>({ locked: true, armed: false });
  const [hydrated, setHydrated] = React.useState<boolean>(false);

  function setSession(patch: Partial<SessionState>) {
    setSessionState((s) => ({ ...s, ...patch }));
  }

  async function unlockOperator(): Promise<boolean> {
    if (state.role !== 'operator') {
      setSessionState({ locked: false, armed: false });
      return true;
    }
    if (state.adminKey) {
      setSessionState((s) => ({ ...s, locked: false }));
      return true;
    }
    const key = await getSecureString(
      'victor.adminKey',
      state.biometricsEnabled
        ? { requireAuthentication: true, authenticationPrompt: 'Unlock x∆v operator key' }
        : undefined,
    );
    if (!key) return false;
    dispatch({ type: 'set', patch: { adminKey: key, hasAdminKeySecure: true } });
    setSessionState((s) => ({ ...s, locked: false, armed: false }));
    return true;
  }

  async function lockOperator(): Promise<void> {
    setSessionState({ locked: true, armed: false });
    if (state.role === 'operator') {
      dispatch({ type: 'set', patch: { adminKey: '' } });
    }
  }

  async function refreshMultichain() {
    try {
      if (!state.baseUrl) throw new Error('no_base_url');
      const r = await fetchChains(state.baseUrl);
      const chains = (r?.chains ?? []).map((x: unknown) => String(x));
      const active = String(r?.active ?? state.activeChain ?? state.chain ?? '');
      setMultichain({ ok: !!r?.ok, active, chains, last_refresh_ms: Date.now() });
      dispatch({ type: 'set', patch: { activeChain: active } });
    } catch {
      const fallback = String(state.activeChain ?? state.chain ?? '');
      setMultichain({ ok: false, active: fallback, chains: fallback ? [fallback] : [], last_refresh_ms: Date.now() });
    }
  }

  async function selectActiveChain(chain: string) {
    const c = String(chain || '');
    if (!c) return;
    if (!state.baseUrl || state.role !== 'operator' || session.locked) {
      dispatch({ type: 'set', patch: { activeChain: c, chain: c } });
      setMultichain({ ok: false, active: c, chains: multichain.chains.length ? multichain.chains : [c], last_refresh_ms: Date.now() });
      return;
    }
    try {
      const r = await selectChain(state.baseUrl, c, state.adminKey);
      const active = String(r?.active ?? c);
      const chains = (r?.chains ?? multichain.chains ?? []).map((x: unknown) => String(x));
      setMultichain({ ok: !!r?.ok, active, chains, last_refresh_ms: Date.now() });
      dispatch({ type: 'set', patch: { activeChain: active, chain: active } });
    } catch {
      setMultichain({ ok: false, active: c, chains: multichain.chains.length ? multichain.chains : [c], last_refresh_ms: Date.now() });
      dispatch({ type: 'set', patch: { activeChain: c, chain: c } });
    }
  }

  const api = useMemo(
    () => ({
      state,
      set: (patch: Partial<AppSettings>) => dispatch({ type: 'set', patch }),
      reset: () => dispatch({ type: 'reset' }),
      session,
      setSession,
      unlockOperator,
      lockOperator,
      multichain,
      refreshMultichain,
      selectActiveChain,
      hydrated,
    }),
    [state, session, multichain, hydrated],
  );

  useEffect(() => {
    (async () => {
      let patch: Partial<AppSettings> = {};
      try {
        const raw = await AsyncStorage.getItem('victor.settings');
        if (raw) {
          patch = JSON.parse(raw) as Partial<AppSettings>;
          dispatch({ type: 'set', patch });
        }
      } catch {}
      const boot = { ...DEFAULTS, ...patch };
      if (boot.role === 'operator') {
        if (boot.biometricsEnabled) {
          dispatch({ type: 'set', patch: { adminKey: '', hasAdminKeySecure: !!boot.hasAdminKeySecure } });
        } else {
          try {
            const k = await getSecureString('victor.adminKey');
            if (k) dispatch({ type: 'set', patch: { adminKey: k, hasAdminKeySecure: true } });
          } catch {}
        }
      }
      setHydrated(true);
    })();
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    if (state.role !== 'operator') {
      setSessionState({ locked: false, armed: false });
      return;
    }
    if (!state.adminKey && !state.hasAdminKeySecure) {
      setSessionState((s) => ({ ...s, locked: true, armed: false }));
      return;
    }
    setSessionState((s) => ({ ...s, locked: true, armed: false }));
  }, [hydrated, state.role, state.hasAdminKeySecure, state.adminKey]);

  useEffect(() => {
    if (!hydrated) return;
    (async () => {
      try {
        const safe = { ...state, adminKey: '' };
        await AsyncStorage.setItem('victor.settings', JSON.stringify(safe));
      } catch {}
    })();
  }, [hydrated, state]);

  useEffect(() => {
    if (!hydrated) return;
    (async () => {
      try {
        if (state.role === 'operator' && state.adminKey) {
          await setSecureString(
            'victor.adminKey',
            String(state.adminKey || ''),
            state.biometricsEnabled
              ? { requireAuthentication: true, authenticationPrompt: 'Unlock x∆v operator key' }
              : undefined,
          );
          if (!state.hasAdminKeySecure) {
            dispatch({ type: 'set', patch: { hasAdminKeySecure: true } });
          }
          return;
        }
        if (state.role !== 'operator' && state.hasAdminKeySecure) {
          await deleteSecureString('victor.adminKey');
          dispatch({ type: 'set', patch: { hasAdminKeySecure: false } });
        }
      } catch {}
    })();
  }, [hydrated, state.adminKey, state.role, state.biometricsEnabled, state.hasAdminKeySecure]);

  useEffect(() => {
    if (!hydrated || !state.baseUrl) return;
    void refreshMultichain();
  }, [hydrated, state.baseUrl]);

  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}

export function useStore() {
  const v = useContext(Ctx);
  if (!v) throw new Error('StoreProvider missing');
  return v;
}
