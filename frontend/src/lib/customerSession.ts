import type { Session } from '../types';
import { hasTelegramLaunchParameters, isTelegramMiniApp, loadTelegramWebApp } from './telegram';

// Launch hint only; never used to authenticate. No credentials go into browser storage.
const launchExpected =
  typeof window !== 'undefined' && hasTelegramLaunchParameters(window.location);
let csrf = '';
let established = false;
let restoring: Promise<Session> | undefined;
export class CustomerAuthError extends Error {
  constructor(
    message: string,
    public status?: number,
  ) {
    super(message);
  }
}
export function restoreCustomerSession(force = false): Promise<Session> {
  if (restoring) return restoring;
  restoring = (async () => {
    await loadTelegramWebApp();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      const read = await fetch('/api/session/', {
        credentials: 'same-origin',
        cache: 'no-store',
        signal: controller.signal,
      });
      if (!read.ok)
        throw new CustomerAuthError(
          'Не удалось восстановить вход. Повторите попытку.',
          read.status,
        );
      const session: Session = await read.json();
      csrf = session.csrf_token || '';
      const raw = window.Telegram?.WebApp?.initData;
      if (raw && (!established || force || !session.authenticated)) {
        const login = await fetch('/api/session/login/', {
          method: 'POST',
          credentials: 'same-origin',
          signal: controller.signal,
          headers: { Authorization: `tma ${raw}`, 'X-CSRFToken': csrf },
        });
        if (login.ok) {
          const verified: Session = await login.json();
          csrf = verified.csrf_token || csrf;
          established = true;
          const proof = await fetch('/api/session/', {
            credentials: 'same-origin',
            cache: 'no-store',
            signal: controller.signal,
          });
          if (!proof.ok)
            throw new CustomerAuthError(
              'Не удалось проверить сохранение сессии. Повторите попытку.',
              proof.status,
            );
          const stored: Session = await proof.json();
          if (!stored.authenticated)
            throw new CustomerAuthError(
              'Браузер не сохранил cookie входа. Разрешите cookie или откройте магазин в приложении Telegram.',
              401,
            );
          csrf = stored.csrf_token || csrf;
          return verified;
        }
        // Expired launch data cannot renew a session, but cannot invalidate an existing one.
        if (login.status !== 401 || !session.authenticated)
          throw new CustomerAuthError(
            'Вход через Telegram не подтверждён. Откройте магазин заново из меню бота.',
            login.status,
          );
      }
      if (
        !session.authenticated &&
        !raw &&
        (launchExpected || isTelegramMiniApp(window.Telegram?.WebApp))
      )
        throw new CustomerAuthError(
          'Действующая сессия не найдена, Telegram ещё не передал данные входа. Повторите проверку или откройте магазин из меню бота.',
          401,
        );
      return session;
    } finally {
      clearTimeout(timer);
    }
  })().finally(() => {
    restoring = undefined;
  });
  return restoring;
}

export async function customerFetch(path: string, init: RequestInit = {}): Promise<Response> {
  if (!/^\/api\/(orders|profile|cart)(\/|\?|$)/.test(path)) return fetch(path, init);
  const send = () =>
    fetch(path, {
      ...init,
      credentials: 'same-origin',
      headers: {
        ...init.headers,
        ...(!['GET', 'HEAD'].includes(init.method || 'GET') ? { 'X-CSRFToken': csrf } : {}),
      },
    });
  let response = await send();
  let csrfFailure = false;
  if (response.status === 403) {
    const data = await response
      .clone()
      .json()
      .catch(() => null);
    csrfFailure = typeof data?.detail === 'string' && data.detail.startsWith('CSRF Failed');
  }
  if (response.status === 401 || csrfFailure) {
    let session: Session;
    try {
      session = await restoreCustomerSession(true);
    } catch (error) {
      if (error instanceof CustomerAuthError && error.status === 401) {
        window.dispatchEvent(new Event('miniapp:session-expired'));
        return new Response(JSON.stringify({ detail: error.message }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      throw error;
    }
    if (session.authenticated) response = await send();
    else window.dispatchEvent(new Event('miniapp:session-expired'));
  }
  return response;
}
