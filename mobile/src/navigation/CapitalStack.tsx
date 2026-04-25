import React from 'react';
import { createStackNavigator } from '@react-navigation/stack';
import { CapitalArchitectureScreen } from '../screens/cc/CapitalArchitectureScreen';
import { LaunchSetupScreen } from '../screens/LaunchSetupScreen';
import { LaunchDashboardScreen } from '../screens/LaunchDashboardScreen';
import { FamilyReadinessScreen } from '../screens/FamilyReadinessScreen';
import { OffRampScreen } from '../screens/cc/OffRampScreen';
import { WalletScreen } from '../screens/v2/WalletScreen';
import { LedgerScreen } from '../screens/v2/LedgerScreen';

export type CapitalStackParamList = {
  CapitalHome: undefined;
  LaunchSetup: undefined;
  LaunchDashboard: undefined;
  FamilyReadiness: undefined;
  OffRamp: undefined;
  Wallet: undefined;
  Ledger: undefined;
};

const Stack = createStackNavigator<CapitalStackParamList>();

export function CapitalStack() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="CapitalHome" component={CapitalArchitectureScreen} />
      <Stack.Screen name="LaunchSetup" component={LaunchSetupScreen} />
      <Stack.Screen name="LaunchDashboard" component={LaunchDashboardScreen} />
      <Stack.Screen name="FamilyReadiness" component={FamilyReadinessScreen} />
      <Stack.Screen name="OffRamp" component={OffRampScreen} />
      <Stack.Screen name="Wallet" component={WalletScreen} />
      <Stack.Screen name="Ledger" component={LedgerScreen} />
    </Stack.Navigator>
  );
}
