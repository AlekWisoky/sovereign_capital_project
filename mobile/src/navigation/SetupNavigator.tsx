import React from "react";
import { createStackNavigator } from "@react-navigation/stack";
import { useStore } from "../state/store";
import { SetupScreen } from "../screens/v2/SetupScreen";
import { LoginScreen } from "../screens/v2/LoginScreen";
import { MainTabs } from "./MainTabs";

export type RootStackParamList = {
  Setup: undefined;
  Login: undefined;
  Main: undefined;
};

const Stack = createStackNavigator<RootStackParamList>();

export function RootStack() {
  const { state, session } = useStore();

  const needsSetup = !state.onboarded;
  const needsLogin = state.onboarded && state.role === "operator" && session.locked;

  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      {needsSetup ? (
        <Stack.Screen name="Setup" component={SetupScreen} />
      ) : needsLogin ? (
        <Stack.Screen name="Login" component={LoginScreen} />
      ) : (
        <Stack.Screen name="Main" component={MainTabs} />
      )}
    </Stack.Navigator>
  );
}
