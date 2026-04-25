import React from 'react';
import { createStackNavigator } from '@react-navigation/stack';
import { SandboxLabScreen } from '../screens/cc/SandboxLabScreen';
import { TrackerScreen } from '../screens/v2/TrackerScreen';
import { AgentsScreen } from '../screens/v2/AgentsScreen';

export type LabStackParamList = {
  LabOverview: undefined;
  Tracker: undefined;
  Agents: undefined;
};

const Stack = createStackNavigator<LabStackParamList>();

export function LabStack() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="LabOverview" component={SandboxLabScreen} />
      <Stack.Screen name="Tracker" component={TrackerScreen} />
      <Stack.Screen name="Agents" component={AgentsScreen} />
    </Stack.Navigator>
  );
}
