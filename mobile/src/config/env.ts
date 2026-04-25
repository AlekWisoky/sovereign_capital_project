import { Platform } from 'react-native';

type WebWindow = typeof window & { location?: Location };

function hasWindow(): boolean {
  return typeof window !== 'undefined';
}

function getWindowLocation(): Location | null {
  if (!hasWindow()) return null;
  return ((window as WebWindow).location ?? null) as Location | null;
}

function isLocalWebHost(location: Location | null): boolean {
  if (!location) return false;
  const host = String(location.hostname || '').toLowerCase();
  return host === 'localhost' || host === '127.0.0.1' || host === '0.0.0.0';
}

function resolveDefaultBackendUrl(): string {
  const explicit = String(process.env.EXPO_PUBLIC_DEFAULT_BACKEND_URL || '').trim().replace(/\/$/, '');
  if (explicit) return explicit;

  const location = getWindowLocation();
  if (Platform.OS === 'web') {
    if (isLocalWebHost(location)) {
      return 'http://localhost:8000';
    }
    return '';
  }

  return 'http://localhost:8000';
}

export const ENV = {
  appEnv: String(process.env.EXPO_PUBLIC_APP_ENV || 'development'),
  defaultBackendUrl: resolveDefaultBackendUrl(),
  walletConnectProjectId: String(process.env.EXPO_PUBLIC_WALLETCONNECT_PROJECT_ID || '').trim(),
  defaultChain: String(process.env.EXPO_PUBLIC_DEFAULT_CHAIN || 'ethereum').trim(),
  netlifyAppUrl: String(process.env.EXPO_PUBLIC_APP_URL || '').trim(),
  isWeb: Platform.OS === 'web',
};

export function getBackendOriginHint(): string {
  if (ENV.defaultBackendUrl) return ENV.defaultBackendUrl;
  if (ENV.isWeb) return 'Set EXPO_PUBLIC_DEFAULT_BACKEND_URL for production web builds.';
  return 'http://localhost:8000';
}
