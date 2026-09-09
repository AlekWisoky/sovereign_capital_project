import React, { useEffect, useMemo } from 'react';
import { Platform } from 'react-native';
import { WalletConnectModal, useWalletConnectModal } from '@walletconnect/modal-react-native';
import { ENV } from '../config/env';
import { setWalletConnectSession } from '../walletConnect/session';

function WalletConnectSessionMount({ projectId, providerMetadata }: { projectId: string; providerMetadata: unknown }) {
  const { open, isConnected, provider, address } = useWalletConnectModal();

  useEffect(() => {
    setWalletConnectSession({ provider, address, isConnected, open });
    return () => setWalletConnectSession({ provider: null, address: '', isConnected: false, open: null });
  }, [address, isConnected, open, provider]);

  return <WalletConnectModal projectId={projectId} providerMetadata={providerMetadata} />;
}

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

  if (Platform.OS === 'web' || !projectId) return null;
  return <WalletConnectSessionMount projectId={projectId} providerMetadata={providerMetadata} />;
}
