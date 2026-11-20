import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  closeTelegramDialog,
  createTelegramSdkLoader,
  hasTelegramLaunchParameters,
  initializeTelegramAppearance,
  isTelegramMiniApp,
  supportsTelegramVersion,
  TELEGRAM_SDK_URL,
  telegramBackFallback,
  trackAppHistory,
} from './telegram';
import type { TelegramWebApp } from '../types/telegram';

function webApp(overrides: Partial<TelegramWebApp> = {}): TelegramWebApp {
  return {
    platform: 'android',
    version: '8.0',
    ready: vi.fn(),
    expand: vi.fn(),
    requestFullscreen: vi.fn(),
    disableVerticalSwipes: vi.fn(),
    setHeaderColor: vi.fn(),
    onEvent: vi.fn(),
    offEvent: vi.fn(),
    viewportStableHeight: 720,
    safeAreaInset: { top: 24, right: 0, bottom: 16, left: 0 },
    contentSafeAreaInset: { top: 56, right: 0, bottom: 0, left: 0 },
    ...overrides,
  };
}

function cssRoot() {
  const values = new Map<string, string>();
  const root = {
    style: {
      setProperty: (name: string, value: string) => values.set(name, value),
      removeProperty: (name: string) => values.delete(name),
    },
    dataset: {} as Record<string, string>,
  } as unknown as HTMLElement;
  return { root, values };
}

function loaderEnvironment(hash = '') {
  const browser = { location: { search: '', hash } } as unknown as Window;
  const script = {} as HTMLScriptElement;
  const append = vi.fn();
  const createElement = vi.fn(() => script);
  const document = { createElement, head: { append } } as unknown as Document;
  return {
    browser,
    script,
    append,
    createElement,
    loader: createTelegramSdkLoader({ getWindow: () => browser, getDocument: () => document }),
  };
}

afterEach(() => vi.useRealTimers());

describe('Telegram SDK bootstrap and presentation', () => {
  it('does not download the SDK or change a normal browser', async () => {
    const environment = loaderEnvironment();
    expect(await environment.loader()).toBeNull();
    expect(environment.createElement).not.toHaveBeenCalled();
    expect(isTelegramMiniApp(webApp({ platform: 'unknown' }))).toBe(false);
    const { root, values } = cssRoot();
    const app = webApp({ platform: 'unknown' });
    initializeTelegramAppearance(app, root)();
    expect(values.size).toBe(0);
    expect(app.ready).not.toHaveBeenCalled();
  });

  it('recognizes documented launch parameters without requiring user data', () => {
    expect(
      hasTelegramLaunchParameters({
        search: '',
        hash: '#tgWebAppPlatform=ios&tgWebAppVersion=8.0',
      }),
    ).toBe(true);
    expect(
      hasTelegramLaunchParameters({
        search: '?tgWebAppPlatform=web&tgWebAppVersion=8.0',
        hash: '',
      }),
    ).toBe(true);
    expect(hasTelegramLaunchParameters({ search: '?search=сыр', hash: '#description' })).toBe(
      false,
    );
    expect(isTelegramMiniApp(webApp())).toBe(true);
  });

  it('loads the official HTTPS SDK once and sends no referrer', async () => {
    const environment = loaderEnvironment('#tgWebAppPlatform=android&tgWebAppVersion=8.0');
    const first = environment.loader();
    const second = environment.loader();
    expect(first).toBe(second);
    expect(environment.append).toHaveBeenCalledTimes(1);
    expect(environment.script.src).toBe(TELEGRAM_SDK_URL);
    expect(environment.script.referrerPolicy).toBe('no-referrer');
    const app = webApp();
    environment.browser.Telegram = { WebApp: app };
    environment.script.onload?.(new Event('load'));
    expect(await first).toBe(app);
    // ready/expand wait until the essential React shell has mounted.
    expect(app.ready).not.toHaveBeenCalled();
  });

  it('falls back to the browser when the SDK fails or times out', async () => {
    vi.useFakeTimers();
    const failed = loaderEnvironment('#tgWebAppPlatform=ios&tgWebAppVersion=8.0');
    const failure = failed.loader();
    failed.script.onerror?.(new Event('error'));
    expect(await failure).toBeNull();
    const slow = loaderEnvironment('#tgWebAppPlatform=ios&tgWebAppVersion=8.0');
    const timeout = slow.loader();
    await vi.advanceTimersByTimeAsync(4_000);
    expect(await timeout).toBeNull();
  });

  it('initializes ready/expand once across remounts and pairs all event subscriptions', () => {
    const app = webApp();
    const { root, values } = cssRoot();
    const cleanup = initializeTelegramAppearance(app, root);
    expect(app.ready).toHaveBeenCalledTimes(1);
    expect(app.expand).toHaveBeenCalledTimes(1);
    expect(values.get('--app-tg-system-top')).toBe('24px');
    expect(values.get('--app-tg-content-top')).toBe('56px');
    expect(values.get('--app-viewport-stable-height')).toBe('720px');
    const subscriptions = vi.mocked(app.onEvent).mock.calls;
    expect(subscriptions.map(([event]) => event)).toEqual([
      'viewportChanged',
      'safeAreaChanged',
      'contentSafeAreaChanged',
      'fullscreenChanged',
      'fullscreenFailed',
    ]);
    expect(app.disableVerticalSwipes).toHaveBeenCalledTimes(1);
    expect(app.requestFullscreen).toHaveBeenCalledTimes(1);
    expect(app.setHeaderColor).toHaveBeenCalledWith('#ffffff');
    app.safeAreaInset = { top: 0, bottom: 34 };
    app.viewportStableHeight = 680;
    subscriptions[1][1]();
    expect(values.get('--app-tg-system-bottom')).toBe('34px');
    expect(values.get('--app-viewport-stable-height')).toBe('680px');
    cleanup();
    expect(values.size).toBe(0);
    expect(root.dataset.telegramMiniApp).toBeUndefined();
    expect(vi.mocked(app.offEvent).mock.calls).toEqual(subscriptions);
    initializeTelegramAppearance(app, root)();
    expect(app.ready).toHaveBeenCalledTimes(1);
    expect(app.expand).toHaveBeenCalledTimes(1);
    expect(app.requestFullscreen).toHaveBeenCalledTimes(1);
    expect(app.disableVerticalSwipes).toHaveBeenCalledTimes(1);
  });

  it('guards modern insets on old clients and rejects invalid viewport values', () => {
    const app = webApp({ version: '7.10', viewportStableHeight: Number.NaN });
    const { root, values } = cssRoot();
    initializeTelegramAppearance(app, root)();
    expect(vi.mocked(app.onEvent).mock.calls.map(([event]) => event)).toEqual(['viewportChanged']);
    expect(values.size).toBe(0);
    expect(supportsTelegramVersion(app, '8.0')).toBe(false);
    expect(supportsTelegramVersion(app, '6.1')).toBe(true);
    expect(supportsTelegramVersion(webApp({ version: 'invalid' }), '8.0')).toBe(false);
  });

  it('waits for native fullscreen confirmation, updates insets on exit and does not fight user exit', () => {
    const app = webApp();
    const { root, values } = cssRoot();
    const cleanup = initializeTelegramAppearance(app, root);
    expect(root.dataset.telegramFullscreen).toBe('windowed');
    app.isFullscreen = true;
    app.safeAreaInset = { top: 59, bottom: 34 };
    app.contentSafeAreaInset = { top: 52 };
    vi.mocked(app.onEvent).mock.calls.find(([event]) => event === 'fullscreenChanged')![1]();
    expect(root.dataset.telegramFullscreen).toBe('active');
    expect(values.get('--app-tg-system-top')).toBe('59px');
    expect(values.get('--app-tg-content-top')).toBe('52px');
    app.isFullscreen = false;
    app.contentSafeAreaInset = { top: 0 };
    vi.mocked(app.onEvent).mock.calls.find(([event]) => event === 'fullscreenChanged')![1]();
    expect(root.dataset.telegramFullscreen).toBe('windowed');
    expect(values.get('--app-tg-content-top')).toBe('0px');
    expect(app.requestFullscreen).toHaveBeenCalledTimes(1);
    cleanup();
    expect(root.dataset.telegramFullscreen).toBeUndefined();
  });

  it('handles native failure, missing methods and thrown unsupported errors without a retry loop', () => {
    for (const requestFullscreen of [
      undefined,
      vi.fn(),
      vi.fn(() => {
        throw new Error('unsupported');
      }),
    ]) {
      const app = webApp({ requestFullscreen });
      const { root } = cssRoot();
      const cleanup = initializeTelegramAppearance(app, root);
      vi.mocked(app.onEvent).mock.calls.find(([event]) => event === 'fullscreenFailed')![1]();
      expect(root.dataset.telegramFullscreen).toBe('windowed');
      expect(app.expand).toHaveBeenCalledTimes(1);
      if (requestFullscreen) expect(requestFullscreen).toHaveBeenCalledTimes(1);
      cleanup();
    }
  });

  it('does not request fullscreen when already fullscreen; accepts synchronous native changes', () => {
    const app = webApp({ isFullscreen: true });
    const { root } = cssRoot();
    initializeTelegramAppearance(app, root)();
    expect(app.requestFullscreen).not.toHaveBeenCalled();
    const synchronous = webApp();
    synchronous.requestFullscreen = vi.fn(() => {
      synchronous.isFullscreen = true;
    });
    const cleanup = initializeTelegramAppearance(synchronous, root);
    expect(root.dataset.telegramFullscreen).toBe('active');
    cleanup();
  });

  it('guards each optional capability by version and tolerates swipe/header rejection', () => {
    for (const version of ['6.1', '7.6', '7.7', '7.10']) {
      const app = webApp({ version });
      initializeTelegramAppearance(app, cssRoot().root)();
      expect(app.requestFullscreen).not.toHaveBeenCalled();
      expect(vi.mocked(app.onEvent).mock.calls.map(([event]) => event)).toEqual([
        'viewportChanged',
      ]);
      expect(app.disableVerticalSwipes).toHaveBeenCalledTimes(
        version === '7.7' || version === '7.10' ? 1 : 0,
      );
    }
    const app = webApp({
      disableVerticalSwipes: vi.fn(() => {
        throw new Error('unavailable');
      }),
      setHeaderColor: vi.fn(() => {
        throw new Error('unavailable');
      }),
    });
    expect(() => initializeTelegramAppearance(app, cssRoot().root)()).not.toThrow();
    expect(app.requestFullscreen).toHaveBeenCalledTimes(1);
  });

  it('sanitizes device insets and clears stale viewport height after an invalid update', () => {
    const app = webApp({ safeAreaInset: { top: -20, right: Infinity, bottom: Number.NaN } });
    const { root, values } = cssRoot();
    const cleanup = initializeTelegramAppearance(app, root);
    expect(values.get('--app-tg-system-top')).toBe('0px');
    expect(values.get('--app-tg-system-right')).toBe('0px');
    expect(values.get('--app-tg-system-bottom')).toBe('0px');
    app.viewportStableHeight = 0;
    vi.mocked(app.onEvent).mock.calls[0][1]();
    expect(values.has('--app-viewport-stable-height')).toBe(false);
    cleanup();
  });
});

describe('Telegram native Back safety', () => {
  it('hides Back on four roots and chooses an internal fallback for direct deep links', () => {
    for (const path of ['/', '/catalog', '/ideas/', '/cart', '/profile'])
      expect(telegramBackFallback(path)).toBeNull();
    expect(telegramBackFallback('/product/4')).toBe('/catalog');
    expect(telegramBackFallback('/ideas/recipes')).toBe('/ideas');
    expect(telegramBackFallback('/profile/store')).toBe('/profile');
    expect(telegramBackFallback('/promotions/weekend')).toBe('/catalog');
  });

  it('only permits history Back through router entries observed inside this app', () => {
    const start = { keys: ['deep-link'], index: 0 };
    expect(start.index > 0).toBe(false);
    const pushed = trackAppHistory(start, 'catalog', 'PUSH');
    expect(pushed.index > 0).toBe(true);
    const back = trackAppHistory(pushed, 'deep-link', 'POP');
    expect(back.index).toBe(0);
    const replaced = trackAppHistory(back, 'replacement', 'REPLACE');
    expect(replaced.keys[0]).toBe('replacement');
    // An unknown POP can be an external/previous browser page, never trust it.
    expect(trackAppHistory(pushed, 'unseen', 'POP')).toEqual({ keys: ['unseen'], index: 0 });
    expect(trackAppHistory(start, 'deep-link', 'PUSH')).toBe(start);
  });

  it('dismisses dialogs through cancel so React state stays in sync', () => {
    const close = vi.fn();
    const dispatchEvent = vi.fn((_event: Event) => true);
    const document = { querySelector: () => ({ dispatchEvent, close }) } as unknown as Document;
    expect(closeTelegramDialog(document)).toBe(true);
    expect(dispatchEvent.mock.calls[0][0]).toMatchObject({ type: 'cancel', cancelable: true });
    expect(close).toHaveBeenCalledTimes(1);
    dispatchEvent.mockReturnValue(false);
    expect(closeTelegramDialog(document)).toBe(true);
    expect(close).toHaveBeenCalledTimes(1);
    expect(closeTelegramDialog({ querySelector: () => null })).toBe(false);
  });
});
