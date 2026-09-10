import React from 'react';
import { createStackNavigator } from '@react-navigation/stack';
import { HomeCommandScreen } from '../screens/cc/HomeCommandScreen';

export type HomeStackParamList = {
  HomeOverview: undefined;
};

const Stack = createStackNavigator<HomeStackParamList>();

export function HomeStack() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="HomeOverview" component={HomeCommandScreen} />
    </Stack.Navigator>
  );
}
