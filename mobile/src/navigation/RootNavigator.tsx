import React from 'react';
import { NavigationContainer, type Theme as NavigationTheme } from '@react-navigation/native';
import { Text, View } from 'react-native';
import { linking } from './linking';
import { RootStack } from './SetupNavigator';
import { StoreProvider, useStore } from '../state/store';
import { TicketsProvider } from '../state/ticketsContext';
import { getTheme } from '../utils/theme';

function BootScreen() {
  const t = getTheme('cyan_ledger');
  return (
    <View style={{ flex: 1, backgroundColor: t.colors.bg0, alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <Text style={{ color: t.colors.cyan, fontSize: 28, fontWeight: '900', letterSpacing: 1 }}>x∆v</Text>
      <Text style={{ color: t.colors.textMuted, marginTop: 12, fontSize: 14 }}>Initializing sovereign control surface…</Text>
    </View>
  );
}

function NavigationShell() {
  const { state, hydrated } = useStore();
  const t = getTheme(state.themeName);
  const navigationTheme: NavigationTheme = {
    dark: true,
    colors: {
      primary: t.colors.cyan,
      background: t.colors.bg0,
      card: t.colors.bg1,
      text: t.colors.text,
      border: t.colors.border,
      notification: t.colors.violet,
    },
  };

  if (!hydrated) return <BootScreen />;

  return (
    <NavigationContainer
      linking={linking}
      theme={navigationTheme}
      documentTitle={{
        formatter: (options, route) => {
          const name = options?.title || route?.name || 'Command Center';
          return `x∆v · ${name}`;
        },
      }}
    >
      <RootStack />
    </NavigationContainer>
  );
}

export default function RootNavigator() {
  return (
    <StoreProvider>
      <TicketsProvider>
        <NavigationShell />
      </TicketsProvider>
    </StoreProvider>
  );
}
