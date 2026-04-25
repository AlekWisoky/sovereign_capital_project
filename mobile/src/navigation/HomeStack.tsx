import React from 'react';
import { createStackNavigator } from '@react-navigation/stack';
import { HomeCommandScreen } from '../screens/cc/HomeCommandScreen';
import { DashScreen } from '../screens/v2/DashScreen';
import { TrackerScreen } from '../screens/v2/TrackerScreen';

export type HomeStackParamList = {
  HomeOverview: undefined;
  Dash: undefined;
  Tracker: undefined;
};

const Stack = createStackNavigator<HomeStackParamList>();

export function HomeStack() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="HomeOverview" component={HomeCommandScreen} />
      <Stack.Screen name="Dash" component={DashScreen} />
      <Stack.Screen name="Tracker" component={TrackerScreen} />
    </Stack.Navigator>
  );
}
