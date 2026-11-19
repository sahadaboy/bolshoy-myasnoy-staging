import type { MouseEvent } from 'react';

/** Native Telegram links when available; ordinary browsers retain real anchors. */
export function openExternal(event: MouseEvent<HTMLAnchorElement>, value: string) {
  if (event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const app = window.Telegram?.WebApp;
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return;
  }
  if (url.protocol !== 'https:') return;
  const native = app as typeof app & {
    openTelegramLink?: (url: string) => void;
    openLink?: (url: string) => void;
  };
  if (!native || native.platform === 'unknown') return;
  try {
    if ((url.hostname === 't.me' || url.hostname === 'telegram.me') && native.openTelegramLink) {
      native.openTelegramLink(value);
      event.preventDefault();
    } else if (native.openLink) {
      native.openLink(value);
      event.preventDefault();
    }
  } catch {
    /* A normal anchor remains usable if this SDK feature is unsupported. */
  }
}
