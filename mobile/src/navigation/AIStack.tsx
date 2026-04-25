import React from 'react';
import { createStackNavigator } from '@react-navigation/stack';
import { MindOfMachineScreen } from '../screens/cc/MindOfMachineScreen';
import { AgentsScreen } from '../screens/v2/AgentsScreen';
import { TrackerScreen } from '../screens/v2/TrackerScreen';

export type AIStackParamList = {
  AIOverview: undefined;
  Agents: undefined;
  Tracker: undefined;
};

const Stack = createStackNavigator<AIStackParamList>();

export function AIStack() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="AIOverview" component={MindOfMachineScreen} />
      <Stack.Screen name="Agents" component={AgentsScreen} />
      <Stack.Screen name="Tracker" component={TrackerScreen} />
    </Stack.Navigator>
  );
}
