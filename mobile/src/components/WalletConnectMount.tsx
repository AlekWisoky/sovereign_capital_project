import React, { useEffect, useMemo } from 'react';
import { Platform } from 'react-native';
import { ENV } from '../config/env';
import { setWalletConnectSession } from '../walletConnect/session';

export function WalletConnectMount() {
  const projectId = ENV.walletConnectProjectId;
  const providerMetadata = useMemo(
    () => ({
      name: 'x∆v',
      description: 'x∆v — Sovereign Capital operator console',
      url: ENV.netlifyAppUrl || 'https://xdv-sovereign-capital.netlify.app',
      icons: ['https://walletconnect.com/walletconnect-logo.png'],
      redirect: {
        native: 'xdv://',
        universal: ENV.netlifyAppUrl || 'https://xdv-sovereign-capital.netlify.app',
      },
    }),
    [],
  );

  if (Platform.OS === 'web' || !projectId) {
    setWalletConnectSession({ provider: null, address: '', isConnected: false, open: null });
    return null;
  }

  try {
    const { useWalletConnectModal, WalletConnectModal } = require('@walletconnect/modal-react-native') as {
      useWalletConnectModal: () => {
        open: () => Promise<unknown>;
        isConnected: boolean;
        provider?: { request: (args: { method: string; params?: unknown[] }) => Promise<unknown> } | null;
        address?: string;
      };
      WalletConnectModal: React.ComponentType<{ projectId: string; providerMetadata: unknown }>;
    };
    const { open, isConnected, provider, address } = useWalletConnectModal();

    useEffect(() => {
      setWalletConnectSession({ provider, address, isConnected, open });
      return () => setWalletConnectSession({ provider: null, address: '', isConnected: false, open: null });
    }, [address, isConnected, open, provider]);

    return <WalletConnectModal projectId={projectId} providerMetadata={providerMetadata} />;
  } catch {
    setWalletConnectSession({ provider: null, address: '', isConnected: false, open: null });
    return null;
  }
}
