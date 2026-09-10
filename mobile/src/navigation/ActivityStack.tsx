import React from "react";
import { createStackNavigator } from "@react-navigation/stack";
import { ActivityScreen } from "../screens/canonical/ActivityScreen";
import { DecisionDetailScreen } from "../screens/canonical/DecisionDetailScreen";

export type ActivityStackParamList = {
  Activity: undefined;
  DecisionDetail: { decisionId: string };
};

const Stack = createStackNavigator<ActivityStackParamList>();

export function ActivityStack() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="Activity" component={ActivityScreen} />
      <Stack.Screen name="DecisionDetail" component={DecisionDetailScreen} />
    </Stack.Navigator>
  );
}
