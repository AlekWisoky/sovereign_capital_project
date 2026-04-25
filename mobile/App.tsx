import './src/walletConnect/bootstrap';
import 'react-native-get-random-values';
import 'react-native-gesture-handler';
import React from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import RootNavigator from './src/navigation/RootNavigator';
import { WalletConnectMount } from './src/components/WalletConnectMount';

export default function App() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <RootNavigator />
        <WalletConnectMount />
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
