import React from 'react';
import { Platform, Text, View } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { useTheme } from '../utils/useTheme';
import { HomeStack } from './HomeStack';
import { CapitalStack } from './CapitalStack';
import { AIStack } from './AIStack';
import { DefensiveLayerScreen } from '../screens/cc/DefensiveLayerScreen';
import { LabStack } from './LabStack';
import { PerformanceScreen } from '../screens/cc/PerformanceScreen';
import { GovernanceRulesScreen } from '../screens/cc/GovernanceRulesScreen';
import { CommandCenterProvider } from '../commandCenter/useCommandCenter';
import { ControlCenterSheet } from '../components/cc/ControlCenterSheet';

export type MainTabsParamList = {
  Home: undefined;
  Capital: undefined;
  AI: undefined;
  Risk: undefined;
  Lab: undefined;
  Analytics: undefined;
  Governance: undefined;
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
          <Tab.Screen name="AI" component={AIStack} options={{ tabBarLabel: 'AI', tabBarIcon: ({ color }) => <Glyph label="AI" color={color} /> }} />
          <Tab.Screen name="Risk" component={DefensiveLayerScreen} options={{ tabBarLabel: 'Risk', tabBarIcon: ({ color }) => <Glyph label="RK" color={color} /> }} />
          <Tab.Screen name="Lab" component={LabStack} options={{ tabBarLabel: 'Lab', tabBarIcon: ({ color }) => <Glyph label="LB" color={color} /> }} />
          <Tab.Screen name="Analytics" component={PerformanceScreen} options={{ tabBarLabel: 'Analytics', tabBarIcon: ({ color }) => <Glyph label="AN" color={color} /> }} />
          <Tab.Screen name="Governance" component={GovernanceRulesScreen} options={{ tabBarLabel: 'Governance', tabBarIcon: ({ color }) => <Glyph label="GV" color={color} /> }} />
        </Tab.Navigator>
        <ControlCenterSheet />
      </View>
    </CommandCenterProvider>
  );
}
