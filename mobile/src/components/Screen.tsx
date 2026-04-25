import React from 'react';
import { View } from 'react-native';
import { theme } from '../utils/theme';
import { WEB_MAX_WIDTH } from '../utils/layout';

export function Screen({ children }: { children: React.ReactNode }) {
  return (
    <View style={{ flex: 1, backgroundColor: theme.bg, padding: 16, width: '100%', maxWidth: WEB_MAX_WIDTH, alignSelf: 'center' }}>
      {children}
    </View>
  );
}
