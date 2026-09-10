import React from "react";
import { createStackNavigator } from "@react-navigation/stack";
import { OpportunitiesScreen } from "../screens/canonical/OpportunitiesScreen";
import { DecisionDetailScreen } from "../screens/canonical/DecisionDetailScreen";

export type OpportunitiesStackParamList = {
  Opportunities: undefined;
  DecisionDetail: { decisionId: string };
};

const Stack = createStackNavigator<OpportunitiesStackParamList>();

export function OpportunitiesStack() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="Opportunities" component={OpportunitiesScreen} />
      <Stack.Screen name="DecisionDetail" component={DecisionDetailScreen} />
    </Stack.Navigator>
  );
}
