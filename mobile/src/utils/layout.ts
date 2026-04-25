import { Platform } from 'react-native';
import type { Theme } from './theme';

export const WEB_MAX_WIDTH = 1440;

export function pageContentContainerStyle(theme: Theme, bottomPad = 40) {
  return {
    padding: theme.spacing.lg,
    paddingBottom: bottomPad,
    width: '100%' as const,
    maxWidth: Platform.OS === 'web' ? WEB_MAX_WIDTH : undefined,
    alignSelf: Platform.OS === 'web' ? ('center' as const) : undefined,
  };
}

export function pageShellStyle(theme: Theme) {
  return {
    flex: 1,
    backgroundColor: theme.colors.bg0,
  };
}
