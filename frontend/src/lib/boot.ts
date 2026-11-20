import { isTelegramMiniApp } from './telegram';

/** Shell readiness only: never wait for catalog, session or photos. */
export function completeBoot(document: Document, browser: Window) {
  const boot = document.getElementById('app-boot');
  if (!boot) return;
  // Telegram's native splash covers bootstrap. Remove ours before WebApp.ready().
  if (
    isTelegramMiniApp(browser.Telegram?.WebApp) ||
    browser.matchMedia('(prefers-reduced-motion: reduce)').matches
  ) {
    boot.remove();
    return;
  }
  boot.dataset.ready = 'true';
  boot.addEventListener('transitionend', () => boot.remove(), { once: true });
  browser.setTimeout(() => boot.remove(), 200); // transition disabled/interrupted fallback
}
