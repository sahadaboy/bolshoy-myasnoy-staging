import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { createOrder, fetchSession } from './api';
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
    location: { origin: 'http://localhost:5174' },
    Telegram: { WebApp: { initData: 'signed-init-data' } },
    setTimeout,
    clearTimeout,
  }),
);
afterEach(() => vi.unstubAllGlobals());

it('sends signed data in the private header without putting it in URLs', async () => {
  const mock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ authenticated: true })));
  vi.stubGlobal('fetch', mock);
  await fetchSession();
  expect(mock.mock.calls[0][0]).toBe('/api/session/');
  expect(mock.mock.calls[0][1].headers.Authorization).toBe('tma signed-init-data');
  expect(mock.mock.calls[0][1].credentials).toBe('omit');
});

it('rejects disabled submissions and malformed success responses', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ detail: 'Приём заявок выключен' }), { status: 503 }),
      ),
  );
  await expect(createOrder(body)).rejects.toThrow('Приём заявок выключен');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }))));
  await expect(createOrder(body)).rejects.toThrow('Сервер не подтвердил');
});

it('only accepts a saved order response and preserves the request key on submission', async () => {
  const mock = vi
    .fn()
    .mockResolvedValue(
      new Response(JSON.stringify({ id: 'saved-id', number: 'БМ-тест', items: [] }), {
        status: 201,
      }),
    );
  vi.stubGlobal('fetch', mock);
  expect((await createOrder(body)).id).toBe('saved-id');
  expect(JSON.parse(mock.mock.calls[0][1].body).request_id).toBe(body.request_id);
});
