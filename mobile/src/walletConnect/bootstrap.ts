import { Platform } from 'react-native';

// WalletConnect React Native polyfills must be loaded before the modal on native.
// We keep this bootstrap as the first import in App.tsx while avoiding web crashes.
if (Platform.OS !== 'web') {
  try {
    require('@walletconnect/react-native-compat');
  } catch {
    // Optional on non-wallet flows; the modal mount already degrades to null when unavailable.
  }
}
