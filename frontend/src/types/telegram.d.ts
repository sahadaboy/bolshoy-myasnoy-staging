export interface TelegramInsets {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export type TelegramViewportEvent =
  'viewportChanged' | 'safeAreaChanged' | 'contentSafeAreaChanged';

export interface TelegramBackButton {
  show: () => unknown;
  hide: () => unknown;
  onClick: (callback: () => void) => unknown;
  offClick: (callback: () => void) => unknown;
}

/** Only the official SDK fields used for presentation. These are not authentication. */
export interface TelegramWebApp {
  initData?: string;
  platform: string;
  version: string;
  ready: () => void;
  expand: () => void;
  isVersionAtLeast?: (version: string) => boolean;
  viewportStableHeight?: number;
  safeAreaInset?: Partial<TelegramInsets>;
  contentSafeAreaInset?: Partial<TelegramInsets>;
  onEvent: (event: TelegramViewportEvent, callback: () => void) => void;
  offEvent: (event: TelegramViewportEvent, callback: () => void) => void;
  BackButton?: TelegramBackButton;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}
