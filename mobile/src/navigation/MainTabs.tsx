import React from 'react';
import { Platform, Text, View } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { useTheme } from '../utils/useTheme';
import { HomeStack } from './HomeStack';
import { CapitalStack } from './CapitalStack';
import { DefensiveLayerScreen } from '../screens/cc/DefensiveLayerScreen';
import { CommandCenterProvider } from '../commandCenter/useCommandCenter';
import { ControlCenterSheet } from '../components/cc/ControlCenterSheet';
import { CanonicalOpportunitiesScreen } from '../screens/CanonicalOpportunitiesScreen';
import { CanonicalOmarScreen } from '../screens/CanonicalOmarScreen';
import { CanonicalActivityScreen } from '../screens/CanonicalActivityScreen';

export type MainTabsParamList = {
  Home: undefined;
  Capital: undefined;
  Opportunities: undefined;
  OMAR: undefined;
  Risk: undefined;
  Activity: undefined;
};

const Tab = createBottomTabNavigator<MainTabsParamList>();

function Glyph({ label, color }: { label: string; color: string }) {
  return <Text style={{ color, fontSize: 14, fontWeight: '900', letterSpacing: 0.5 }}>{label}</Text>;
}

export function MainTabs() {
  const theme = useTheme();
  const isWeb = Platform.OS === 'web';
  return (
    <CommandCenterProvider>
      <View style={{ flex: 1 }}>
        <Tab.Navigator
          screenOptions={{
            headerShown: false,
            tabBarStyle: {
              backgroundColor: theme.colors.bg1,
              borderTopColor: theme.colors.border,
              height: isWeb ? 58 : 66,
              paddingBottom: isWeb ? 8 : 10,
              paddingTop: 8,
            },
            tabBarItemStyle: isWeb ? { maxWidth: 180 } : undefined,
            tabBarActiveTintColor: theme.colors.cyan,
            tabBarInactiveTintColor: theme.colors.textFaint,
            tabBarLabelStyle: {
              fontSize: 11,
              fontWeight: '800',
              letterSpacing: 0.2,
            },
          }}
        >
          <Tab.Screen name="Home" component={HomeStack} options={{ tabBarLabel: 'Home', tabBarIcon: ({ color }) => <Glyph label="HM" color={color} /> }} />
          <Tab.Screen name="Capital" component={CapitalStack} options={{ tabBarLabel: 'Capital', tabBarIcon: ({ color }) => <Glyph label="CP" color={color} /> }} />
          <Tab.Screen name="Opportunities" component={CanonicalOpportunitiesScreen} options={{ tabBarLabel: 'Opportunities', tabBarIcon: ({ color }) => <Glyph label="OP" color={color} /> }} />
          <Tab.Screen name="OMAR" component={CanonicalOmarScreen} options={{ tabBarLabel: 'OMAR', tabBarIcon: ({ color }) => <Glyph label="AI" color={color} /> }} />
          <Tab.Screen name="Risk" component={DefensiveLayerScreen} options={{ tabBarLabel: 'Risk', tabBarIcon: ({ color }) => <Glyph label="RK" color={color} /> }} />
          <Tab.Screen name="Activity" component={CanonicalActivityScreen} options={{ tabBarLabel: 'Activity', tabBarIcon: ({ color }) => <Glyph label="AC" color={color} /> }} />
        </Tab.Navigator>
        <ControlCenterSheet />
      </View>
    </CommandCenterProvider>
  );
}
