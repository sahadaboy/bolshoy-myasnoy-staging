import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { createOrder, fetchSession, updateCustomerPhone } from './api';
import type { OrderRequest } from '../types';

const body: OrderRequest = {
  request_id: '00000000-0000-4000-8000-000000000001',
  buyer_name: 'Тест',
  phone: '+79001234567',
  comment: '',
  items: [{ product_id: 1, quantity: '0.500', expected_price: '100.00' }],
};
beforeEach(() =>
  vi.stubGlobal('window', {
    location: { origin: 'http://localhost:5174', search: '', hash: '' },
    dispatchEvent: vi.fn(),
    Telegram: { WebApp: { initData: 'signed-init-data' } },
    setTimeout,
    clearTimeout,
  }),
);
afterEach(() => vi.unstubAllGlobals());

it('exchanges signed data once for a cookie session, with CSRF and no credentials in URLs', async () => {
  const mock = vi
    .fn()
    .mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify({ authenticated: true, csrf_token: 'csrf' }))),
    );
  vi.stubGlobal('fetch', mock);
  await fetchSession();
  expect(mock.mock.calls[0][0]).toBe('/api/session/');
  expect(mock.mock.calls[1][0]).toBe('/api/session/login/');
  expect(mock.mock.calls[1][1].headers.Authorization).toBe('tma signed-init-data');
  expect(mock.mock.calls[1][1].headers['X-CSRFToken']).toBe('csrf');
  expect(mock.mock.calls[0][1].credentials).toBe('same-origin');
});

it('rejects disabled submissions and malformed success responses', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Приём заявок выключен' }), {
        status: 503,
      }),
    ),
  );
  await expect(createOrder(body)).rejects.toThrow('Приём заявок выключен');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }))));
  await expect(createOrder(body)).rejects.toThrow('Сервер не подтвердил');
});

it('only accepts a saved order response and preserves the request key on submission', async () => {
  const mock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ id: 'saved-id', number: 'БМ-тест', items: [] }), {
      status: 201,
    }),
  );
  vi.stubGlobal('fetch', mock);
  expect((await createOrder(body)).id).toBe('saved-id');
  expect(JSON.parse(mock.mock.calls[0][1].body).request_id).toBe(body.request_id);
});

it('saves the phone through the authenticated profile endpoint independently of orders', async () => {
  const mock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ phone: '+79780000001' })));
  vi.stubGlobal('fetch', mock);
  expect(await updateCustomerPhone('+7 (978) 000-00-01')).toEqual({
    phone: '+79780000001',
  });
  expect(mock.mock.calls[0][0]).toBe('/api/profile/');
  expect(mock.mock.calls[0][1].method).toBe('POST');
  expect(mock.mock.calls[0][1].headers.Authorization).toBeUndefined();
  expect(mock.mock.calls[0][1].credentials).toBe('same-origin');
});

it('never reports phone success for expired authentication, validation errors or malformed responses', async () => {
  const mock = vi
    .fn()
    .mockImplementation((path: string) =>
      Promise.resolve(
        new Response(
          JSON.stringify(
            path === '/api/session/'
              ? { authenticated: false, csrf_token: 'csrf' }
              : { detail: 'expired' },
          ),
          { status: path === '/api/session/' ? 200 : 401 },
        ),
      ),
    );
  vi.stubGlobal('fetch', mock);
  await expect(updateCustomerPhone('123')).rejects.toMatchObject({
    status: 401,
    message: expect.stringContaining('из меню бота'),
  });
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ phone: ['Проверьте номер.'] }), { status: 400 }),
      ),
  );
  await expect(updateCustomerPhone('123')).rejects.toThrow('Проверьте номер');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }))));
  await expect(updateCustomerPhone('123')).rejects.toThrow('не подтвердил сохранение');
});
