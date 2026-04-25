import React, { useMemo } from 'react';
import { Platform } from 'react-native';
import { ENV } from '../config/env';

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

  try {
    const { WalletConnectModal } = require('@walletconnect/modal-react-native') as {
      WalletConnectModal: React.ComponentType<{ projectId: string; providerMetadata: unknown }>;
    };
    return <WalletConnectModal projectId={projectId} providerMetadata={providerMetadata} />;
  } catch {
    return null;
  }
}
