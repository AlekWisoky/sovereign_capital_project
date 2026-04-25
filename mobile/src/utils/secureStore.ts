import { Platform } from 'react-native';

export type SecureStringOptions = {
  requireAuthentication?: boolean;
  authenticationPrompt?: string;
};

const WEB_PREFIX = 'xdv.secure.';

function getWebStorage(options?: SecureStringOptions): Storage | null {
  if (typeof window === 'undefined') return null;
  try {
    if (options?.requireAuthentication && window.sessionStorage) return window.sessionStorage;
    return window.localStorage;
  } catch {
    return null;
  }
}

async function withNativeSecureStore<T>(fn: (mod: any) => Promise<T>): Promise<T | null> {
  try {
    const mod = require('expo-secure-store');
    return await fn(mod);
  } catch {
    return null;
  }
}

export async function getSecureString(key: string, options?: SecureStringOptions): Promise<string | null> {
  if (Platform.OS === 'web') {
    const store = getWebStorage(options);
    if (!store) return null;
    try {
      return store.getItem(`${WEB_PREFIX}${key}`);
    } catch {
      return null;
    }
  }

  const value = await withNativeSecureStore(async (SecureStore) => {
    const v = await SecureStore.getItemAsync(key, {
      requireAuthentication: !!options?.requireAuthentication,
      authenticationPrompt: options?.authenticationPrompt,
    });
    return v ?? null;
  });
  return value ?? null;
}

export async function setSecureString(key: string, value: string, options?: SecureStringOptions): Promise<void> {
  if (Platform.OS === 'web') {
    const store = getWebStorage(options);
    if (!store) return;
    try {
      if (!value) store.removeItem(`${WEB_PREFIX}${key}`);
      else store.setItem(`${WEB_PREFIX}${key}`, value);
    } catch {}
    return;
  }

  await withNativeSecureStore(async (SecureStore) => {
    if (!value) {
      await SecureStore.deleteItemAsync(key);
      return;
    }
    await SecureStore.setItemAsync(key, value, {
      requireAuthentication: !!options?.requireAuthentication,
      authenticationPrompt: options?.authenticationPrompt,
    });
  });
}

export async function deleteSecureString(key: string): Promise<void> {
  if (Platform.OS === 'web') {
    try {
      window.localStorage.removeItem(`${WEB_PREFIX}${key}`);
      window.sessionStorage.removeItem(`${WEB_PREFIX}${key}`);
    } catch {}
    return;
  }

  await withNativeSecureStore(async (SecureStore) => {
    await SecureStore.deleteItemAsync(key);
  });
}
