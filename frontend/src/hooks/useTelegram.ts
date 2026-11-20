import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate, useNavigationType } from 'react-router-dom';
import {
  closeTelegramDialog,
  initializeTelegramAppearance,
  loadTelegramWebApp,
  supportsTelegramVersion,
  telegramBackFallback,
  trackAppHistory,
  type AppHistory,
} from '../lib/telegram';
import type { TelegramWebApp } from '../types/telegram';
import { initializeVisualViewport } from '../lib/viewport';

export function useTelegram(): void {
  const location = useLocation();
  const navigate = useNavigate();
  const action = useNavigationType();
  const [app, setApp] = useState<TelegramWebApp | null>(null);
  const history = useRef<AppHistory>({ keys: [location.key], index: 0 });

  useEffect(() => initializeVisualViewport(document.documentElement, window), []);

  useEffect(() => {
    history.current = trackAppHistory(history.current, location.key, action);
  }, [location.key, action]);

  useEffect(() => {
    let active = true;
    void loadTelegramWebApp().then((loaded) => {
      if (active) setApp(loaded);
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (app) return initializeTelegramAppearance(app, document.documentElement);
  }, [app]);

  useEffect(() => {
    if (!app?.BackButton || !supportsTelegramVersion(app, '6.1')) return;
    const back = app.BackButton;
    const fallback =
      telegramBackFallback(location.pathname) ||
      (location.search && ['/catalog', '/ideas'].includes(location.pathname)
        ? location.pathname
        : null);
    const updateVisibility = () => {
      if (fallback || document.querySelector('dialog[open]')) back.show();
      else back.hide();
    };
    const handleBack = () => {
      if (closeTelegramDialog(document)) return;
      if (!fallback) return;
      if (history.current.index > 0) navigate(-1);
      else navigate(fallback, { replace: true });
    };
    back.onClick(handleBack);
    updateVisibility();
    const observer = new MutationObserver(updateVisibility);
    observer.observe(document.body, { attributes: true, attributeFilter: ['open'], subtree: true });
    return () => {
      observer.disconnect();
      back.offClick(handleBack);
      back.hide();
    };
  }, [app, location.pathname, location.search, navigate]);
}
