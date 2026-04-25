import { Platform, Share } from 'react-native';

async function copyViaDom(text: string): Promise<boolean> {
  if (typeof document === 'undefined') return false;
  const el = document.createElement('textarea');
  el.value = text;
  el.setAttribute('readonly', 'true');
  el.style.position = 'fixed';
  el.style.opacity = '0';
  document.body.appendChild(el);
  el.focus();
  el.select();
  const ok = document.execCommand('copy');
  document.body.removeChild(el);
  return ok;
}

export async function shareText(title: string, text: string): Promise<'native' | 'share' | 'clipboard' | 'manual'> {
  if (Platform.OS !== 'web') {
    await Share.share({ title, message: text });
    return 'native';
  }

  const nav = typeof navigator !== 'undefined' ? navigator : undefined;
  if (nav && typeof nav.share === 'function') {
    await nav.share({ title, text });
    return 'share';
  }
  if (nav?.clipboard && typeof nav.clipboard.writeText === 'function') {
    await nav.clipboard.writeText(text);
    return 'clipboard';
  }
  const copied = await copyViaDom(text);
  return copied ? 'clipboard' : 'manual';
}
