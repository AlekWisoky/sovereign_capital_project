import React from "react";
import { createStackNavigator } from "@react-navigation/stack";
import { DefensiveLayerScreen } from "../screens/cc/DefensiveLayerScreen";
import { GovernanceRulesScreen } from "../screens/cc/GovernanceRulesScreen";
import { LaunchDashboardScreen } from "../screens/LaunchDashboardScreen";

export type RiskStackParamList = {
  Risk: undefined;
  Governance: undefined;
  Launch: undefined;
};

const Stack = createStackNavigator<RiskStackParamList>();

export function RiskStack() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="Risk" component={DefensiveLayerScreen} />
      <Stack.Screen name="Governance" component={GovernanceRulesScreen} />
      <Stack.Screen name="Launch" component={LaunchDashboardScreen} />
    </Stack.Navigator>
  );
}
