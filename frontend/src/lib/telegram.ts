import type { TelegramViewportEvent, TelegramWebApp } from '../types/telegram';

// Current official URL documented at https://core.telegram.org/bots/webapps.
export const TELEGRAM_SDK_URL = 'https://telegram.org/js/telegram-web-app.js?65';
const SDK_TIMEOUT_MS = 4_000;
const initializedApps = new WeakSet<TelegramWebApp>();
const rootRoutes = new Set(['/', '/catalog', '/ideas', '/cart', '/profile']);
const edges = ['top', 'right', 'bottom', 'left'] as const;

/** A client-side presentation hint only. It never grants access or authenticates a user. */
export function isTelegramMiniApp(app: TelegramWebApp | null | undefined): app is TelegramWebApp {
  return Boolean(
    app && app.platform && app.platform !== 'unknown' && typeof app.ready === 'function',
  );
}

export function hasTelegramLaunchParameters(location: Pick<Location, 'search' | 'hash'>): boolean {
  return [location.search, location.hash].some((part) => {
    const params = new URLSearchParams(part.replace(/^[#?]/, ''));
    return Boolean(params.get('tgWebAppPlatform') && params.get('tgWebAppVersion'));
  });
}

interface SdkEnvironment {
  getWindow: () => Window | undefined;
  getDocument: () => Document | undefined;
}

/** One loader per page; browsers without launch parameters make no SDK request. */
export function createTelegramSdkLoader(environment: SdkEnvironment) {
  let pending: Promise<TelegramWebApp | null> | undefined;
  return function load(): Promise<TelegramWebApp | null> {
    if (pending) return pending;
    const browser = environment.getWindow();
    const document = environment.getDocument();
    const existing = browser?.Telegram?.WebApp;
    if (isTelegramMiniApp(existing)) return (pending = Promise.resolve(existing));
    if (!browser || !document || !hasTelegramLaunchParameters(browser.location)) {
      return (pending = Promise.resolve(null));
    }
    pending = new Promise((resolve) => {
      const script = document.createElement('script');
      script.id = 'telegram-webapp-sdk';
      script.src = TELEGRAM_SDK_URL;
      script.async = true;
      script.referrerPolicy = 'no-referrer';
      let finished = false;
      const finish = () => {
        if (finished) return;
        finished = true;
        clearTimeout(timeout);
        script.onload = null;
        script.onerror = null;
        const app = browser.Telegram?.WebApp;
        resolve(isTelegramMiniApp(app) ? app : null);
      };
      const timeout = setTimeout(finish, SDK_TIMEOUT_MS);
      script.onload = finish;
      script.onerror = finish;
      try {
        document.head.append(script);
      } catch {
        finish();
      }
    });
    return pending;
  };
}

export const loadTelegramWebApp = createTelegramSdkLoader({
  getWindow: () => (typeof window === 'undefined' ? undefined : window),
  getDocument: () => (typeof document === 'undefined' ? undefined : document),
});

export function supportsTelegramVersion(app: TelegramWebApp, required: string): boolean {
  if (app.isVersionAtLeast) return app.isVersionAtLeast(required);
  const actualParts = app.version.split('.').map(Number);
  const requiredParts = required.split('.').map(Number);
  for (let index = 0; index < Math.max(actualParts.length, requiredParts.length); index += 1) {
    const actual = actualParts[index] ?? 0;
    const minimum = requiredParts[index] ?? 0;
    if (!Number.isFinite(actual) || !Number.isFinite(minimum)) return false;
    if (actual !== minimum) return actual > minimum;
  }
  return true;
}

function inset(value: number | undefined): number {
  return typeof value === 'number' && Number.isFinite(value) ? Math.max(0, value) : 0;
}

/** Subscribe only to version-supported SDK events and clean up on unmount. */
export function initializeTelegramAppearance(app: TelegramWebApp, root: HTMLElement): () => void {
  if (!isTelegramMiniApp(app)) return () => {};
  const supportsInsets = supportsTelegramVersion(app, '8.0');
  const properties = edges.flatMap((edge) => [
    `--app-tg-system-${edge}`,
    `--app-tg-content-${edge}`,
  ]);
  properties.push('--app-viewport-stable-height');
  const sync = () => {
    root.dataset.telegramFullscreen = app.isFullscreen ? 'active' : 'windowed';
    for (const edge of edges) {
      root.style.setProperty(
        `--app-tg-system-${edge}`,
        `${supportsInsets ? inset(app.safeAreaInset?.[edge]) : 0}px`,
      );
      root.style.setProperty(
        `--app-tg-content-${edge}`,
        `${supportsInsets ? inset(app.contentSafeAreaInset?.[edge]) : 0}px`,
      );
    }
    const height = inset(app.viewportStableHeight);
    if (height > 0) root.style.setProperty('--app-viewport-stable-height', `${height}px`);
    else root.style.removeProperty('--app-viewport-stable-height');
  };
  const events: TelegramViewportEvent[] = ['viewportChanged'];
  if (supportsInsets)
    events.push(
      'safeAreaChanged',
      'contentSafeAreaChanged',
      'fullscreenChanged',
      'fullscreenFailed',
    );
  root.dataset.telegramMiniApp = 'true';
  sync();
  events.forEach((event) => app.onEvent(event, sync));
  if (!initializedApps.has(app)) {
    initializedApps.add(app);
    app.ready();
    app.expand();
    // These are optional native capabilities, never a prerequisite for rendering.
    if (supportsTelegramVersion(app, '6.9')) {
      try {
        app.setHeaderColor?.('#ffffff');
      } catch {
        /* retain the native header */
      }
    }
    if (supportsTelegramVersion(app, '7.7')) {
      try {
        app.disableVerticalSwipes?.();
      } catch {
        /* normal page scrolling still works */
      }
    }
    if (supportsInsets && !app.isFullscreen) {
      try {
        app.requestFullscreen?.();
      } catch {
        /* unsupported/denied: keep expanded mode */
      }
    }
    // Some clients update their properties synchronously without emitting an event.
    sync();
  }
  return () => {
    events.forEach((event) => app.offEvent(event, sync));
    properties.forEach((property) => root.style.removeProperty(property));
    delete root.dataset.telegramMiniApp;
    delete root.dataset.telegramFullscreen;
  };
}

export function telegramBackFallback(pathname: string): string | null {
  const path = pathname.replace(/\/+$/, '') || '/';
  if (rootRoutes.has(path)) return null;
  if (path === '/checkout') return '/cart';
  if (path.startsWith('/profile/orders/')) return '/profile/orders';
  if (path.startsWith('/ideas/')) return '/ideas';
  if (path.startsWith('/profile/')) return '/profile';
  return '/catalog';
}

export interface AppHistory {
  keys: string[];
  index: number;
}

/** Track only router keys, never Telegram launch data or external browser history. */
export function trackAppHistory(previous: AppHistory, key: string, action: string): AppHistory {
  if (previous.keys[previous.index] === key) return previous;
  if (action === 'PUSH')
    return {
      keys: [...previous.keys.slice(0, previous.index + 1), key],
      index: previous.index + 1,
    };
  if (action === 'REPLACE') {
    const keys = [...previous.keys];
    keys[previous.index] = key;
    return { keys, index: previous.index };
  }
  const index = previous.keys.indexOf(key);
  return index >= 0 ? { keys: previous.keys, index } : { keys: [key], index: 0 };
}

/** Native Back first dismisses a modal, preserving React onCancel state. */
export function closeTelegramDialog(document: Pick<Document, 'querySelector'>): boolean {
  const dialog = document.querySelector<HTMLDialogElement>('dialog[open]');
  if (!dialog) return false;
  const cancel = new Event('cancel', { cancelable: true });
  if (dialog.dispatchEvent(cancel)) dialog.close();
  return true;
}
