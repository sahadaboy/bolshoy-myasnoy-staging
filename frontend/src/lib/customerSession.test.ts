import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const reply = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
beforeEach(() => {
  vi.resetModules();
  vi.stubGlobal('window', {
    location: { search: '', hash: '' },
    Telegram: { WebApp: { initData: '' } },
    dispatchEvent: vi.fn(),
  });
});
afterEach(() => vi.unstubAllGlobals());
it('restores cookie auth when reload has no initData', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(reply({ authenticated: true, csrf_token: 'token', user: { id: '1' } }));
  vi.stubGlobal('fetch', fetch);
  const { restoreCustomerSession } = await import('./customerSession');
  expect((await restoreCustomerSession()).authenticated).toBe(true);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][1].credentials).toBe('same-origin');
});
it('does not log out an existing cookie session because launch data expired', async () => {
  window.Telegram!.WebApp!.initData = 'old-signed-data';
  const fetch = vi
    .fn()
    .mockImplementation((url: string) =>
      Promise.resolve(
        url.endsWith('/login/')
          ? reply({ detail: 'expired' }, 401)
          : reply({ authenticated: true, csrf_token: 'csrf' }),
      ),
    );
  vi.stubGlobal('fetch', fetch);
  const { restoreCustomerSession } = await import('./customerSession');
  expect((await restoreCustomerSession()).authenticated).toBe(true);
  expect(fetch.mock.calls[1][1].headers.Authorization).toBe('tma old-signed-data');
});
it('deduplicates first login and verifies the browser actually retained the cookie', async () => {
  window.Telegram!.WebApp!.initData = 'signed';
  let logged = false;
  const fetch = vi.fn().mockImplementation((url: string) => {
    if (url.endsWith('/login/')) logged = true;
    return Promise.resolve(
      reply({ authenticated: logged, csrf_token: 'csrf', user: logged ? { id: '1' } : null }),
    );
  });
  vi.stubGlobal('fetch', fetch);
  const { restoreCustomerSession } = await import('./customerSession');
  const sessions = await Promise.all([restoreCustomerSession(), restoreCustomerSession()]);
  expect(sessions.every((s) => s.authenticated)).toBe(true);
  expect(fetch.mock.calls.filter((c) => c[0].endsWith('/login/'))).toHaveLength(1);
});
it('does not pretend to be logged in when session cookies are blocked', async () => {
  window.Telegram!.WebApp!.initData = 'signed';
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockImplementation((url: string) =>
        Promise.resolve(reply({ authenticated: url.endsWith('/login/'), csrf_token: 'csrf' })),
      ),
  );
  const { restoreCustomerSession } = await import('./customerSession');
  await expect(restoreCustomerSession()).rejects.toThrow('cookie');
});
it('does not signal logout on a temporary connection error', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network')));
  const { restoreCustomerSession } = await import('./customerSession');
  await expect(restoreCustomerSession()).rejects.toThrow();
  expect(window.dispatchEvent).not.toHaveBeenCalled();
});
it('refreshes stale CSRF once before retrying an uncommitted write', async () => {
  let attempts = 0;
  const fetch = vi
    .fn()
    .mockImplementation((url: string) =>
      Promise.resolve(
        url === '/api/session/'
          ? reply({ authenticated: true, csrf_token: 'new-csrf' })
          : ++attempts === 1
            ? reply({ detail: 'CSRF Failed: token' }, 403)
            : reply({ phone: 'saved' }),
      ),
    );
  vi.stubGlobal('fetch', fetch);
  const { customerFetch } = await import('./customerSession');
  expect((await customerFetch('/api/profile/', { method: 'POST' })).status).toBe(200);
  expect(fetch.mock.calls[2][1].headers['X-CSRFToken']).toBe('new-csrf');
});
it('only expires after the server confirms the session is gone', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockImplementation((url: string) =>
        Promise.resolve(
          url === '/api/session/'
            ? reply({ authenticated: false, csrf_token: 'csrf' })
            : reply({ detail: 'expired' }, 401),
        ),
      ),
  );
  const { customerFetch } = await import('./customerSession');
  expect((await customerFetch('/api/cart/')).status).toBe(401);
  expect(window.dispatchEvent).toHaveBeenCalled();
});
