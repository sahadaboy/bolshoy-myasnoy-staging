import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { webcrypto } from 'node:crypto';
import { finishOrderRequest, orderRequestId } from './orderRequest';

let values: Map<string, string>;
beforeEach(() => {
  values = new Map();
  vi.stubGlobal('crypto', webcrypto);
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => values.get(key) || null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  });
  finishOrderRequest();
});
afterEach(() => vi.unstubAllGlobals());

it('reuses a request after failure while keeping contact details out of storage', async () => {
  const body = {
    user: '123',
    name: 'Покупатель',
    phone: '+79001234567',
    items: [{ id: 4, quantity: '0.500' }],
  };
  const first = await orderRequestId(body);
  expect(await orderRequestId(body)).toBe(first);
  const stored = [...values.values()].join('');
  expect(stored).not.toContain(body.phone);
  expect(stored).not.toContain(body.name);
  expect(await orderRequestId({ ...body, user: '456' })).not.toBe(first);
});

it('starts a new request after success or changes to the purchase', async () => {
  const first = await orderRequestId({ quantity: 1 });
  expect(await orderRequestId({ quantity: 2 })).not.toBe(first);
  finishOrderRequest();
  expect(await orderRequestId({ quantity: 1 })).not.toBe(first);
});
