import * as Linking from 'expo-linking';
import type { LinkingOptions } from '@react-navigation/native';
import type { RootStackParamList } from './SetupNavigator';

export const linking: LinkingOptions<RootStackParamList> = {
  prefixes: [Linking.createURL('/')],
  config: {
    screens: {
      Setup: 'setup',
      Login: 'login',
      Main: {
        path: '',
        screens: {
          Home: {
            path: '',
            screens: {
              HomeOverview: '',
              Dash: 'dash',
              Tracker: 'tracker',
            },
          },
          Capital: {
            path: 'capital',
            screens: {
              CapitalHome: '',
              LaunchSetup: 'launch-setup',
              LaunchDashboard: 'launch-dashboard',
              FamilyReadiness: 'family-readiness',
              OffRamp: 'off-ramp',
              Wallet: 'wallet',
              Ledger: 'ledger',
            },
          },
          AI: {
            path: 'ai',
            screens: {
              AIOverview: '',
              Agents: 'agents',
              Tracker: 'tracker',
            },
          },
          Risk: 'risk',
          Lab: {
            path: 'lab',
            screens: {
              LabOverview: '',
              Tracker: 'tracker',
              Agents: 'agents',
            },
          },
          Analytics: 'analytics',
          Governance: 'governance',
        },
      },
    },
  },
};
