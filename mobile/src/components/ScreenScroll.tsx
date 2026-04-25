import React from 'react';
import { ScrollView, View } from 'react-native';
import { theme } from '../utils/theme';
import { WEB_MAX_WIDTH } from '../utils/layout';

export function ScreenScroll({ children }: { children: React.ReactNode }) {
  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: theme.bg }}
      contentContainerStyle={{ padding: 16, paddingBottom: 32 }}
      keyboardShouldPersistTaps="handled"
    >
      <View style={{ width: '100%', maxWidth: WEB_MAX_WIDTH, alignSelf: 'center' }}>{children}</View>
    </ScrollView>
  );
}
