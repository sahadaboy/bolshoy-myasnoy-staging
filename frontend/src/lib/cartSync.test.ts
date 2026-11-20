import { afterEach, expect, it, vi } from 'vitest';
import { CartSync } from './cartSync';
import { cartItems, type ServerCart } from './serverCart';
import type { CartItem, Product } from '../types';
const product: Product = {
  id: 1,
  name: 'Товар',
  sku: 'p',
  price: '100.00',
  unit: 'pcs',
  min_quantity: '1.000',
  quantity_step: '1.000',
  is_available: true,
  description: '',
  image: null,
  categories: [],
};
const item = (n: number, id = 1): CartItem => ({ product: { ...product, id }, quantity: n * 1000 });
const snapshot = (revision: number, ...items: CartItem[]): ServerCart => ({
  revision,
  items: items.map((i) => ({
    product_id: i.product.id,
    product: i.product,
    quantity: (i.quantity / 1000).toFixed(3),
  })),
});
const engines: CartSync[] = [];
function setup(initial: CartItem[] = []) {
  const map = new Map<string, string>();
  if (initial.length) map.set('bolshoy-myasnoy.cart.v1', JSON.stringify(initial));
  const storage = {
    getItem: (key: string) => map.get(key) || null,
    setItem: (key: string, value: string) => {
      map.set(key, value);
    },
    removeItem: (key: string) => {
      map.delete(key);
    },
  };
  const read = vi.fn<() => Promise<ServerCart>>().mockResolvedValue(snapshot(0));
  const write = vi.fn().mockResolvedValue(snapshot(1));
  const make = () => {
    const e = new CartSync(
      storage,
      (raw) => (Array.isArray(raw) ? raw : []),
      read,
      write,
      () => {},
      () => {},
    );
    engines.push(e);
    return e;
  };
  return { map, storage, read, write, make };
}
afterEach(() => {
  for (const e of engines) e.dispose();
  engines.length = 0;
});

it('loads server contents without sending an initial empty replacement', async () => {
  const f = setup();
  f.read.mockResolvedValue(snapshot(2, item(3)));
  const e = f.make();
  e.activate('A');
  await e.flush();
  expect(e.items).toEqual([item(3)]);
  expect(f.write).not.toHaveBeenCalled();
  e.activate('guest');
  expect(e.status).toBe('auth-required');
  expect(e.items).toEqual([item(3)]);
});
it('imports guest once and reloads the authenticated cache without doubling it', async () => {
  const f = setup([item(2)]);
  f.read.mockResolvedValue(snapshot(0, item(3)));
  f.write.mockResolvedValue(snapshot(1, item(3)));
  const e = f.make();
  e.activate('A');
  await e.flush();
  expect(f.write.mock.calls[0][0].mode).toBe('merge');
  expect(e.items).toEqual([item(3)]);
  expect(f.map.has('bolshoy-myasnoy.cart.v1')).toBe(false);
  e.dispose();
  f.read.mockResolvedValue(snapshot(1, item(3)));
  const reopened = f.make();
  reopened.activate('A');
  await reopened.flush();
  expect(f.write).toHaveBeenCalledTimes(1);
});
it('retains a pending operation after a lost reply and replays its same UUID before later edits', async () => {
  const f = setup();
  const e = f.make();
  e.activate('A');
  await e.flush();
  f.write
    .mockRejectedValueOnce(new Error('network lost'))
    .mockResolvedValueOnce(snapshot(1, item(2)))
    .mockResolvedValueOnce(snapshot(2, item(4)));
  e.edit([item(2)]);
  await expect(e.flush()).rejects.toThrow();
  const id = f.write.mock.calls[0][0].operation_id;
  e.edit([item(4)]);
  await e.flush();
  expect(f.write.mock.calls[1][0].operation_id).toBe(id);
  expect(e.items).toEqual([item(4)]);
  expect(e.status).toBe('synced');
});
it('preserves edits made during a request, while adopting remote-only products', async () => {
  const f = setup();
  const e = f.make();
  e.activate('A');
  await e.flush();
  let finish!: (v: ServerCart) => void;
  f.write
    .mockImplementationOnce(
      () =>
        new Promise<ServerCart>((resolve) => {
          finish = resolve;
        }),
    )
    .mockResolvedValueOnce(snapshot(2, item(4), item(5, 2)));
  e.edit([item(2)]);
  const flight = e.sync();
  e.edit([item(4)]);
  finish(snapshot(1, item(2), item(5, 2)));
  await flight;
  await e.flush();
  expect(e.items).toEqual([item(4), item(5, 2)]);
});
it('surfaces conflict and keeps local intent; explicit choice merges it with remote-only edits', async () => {
  const f = setup();
  f.read.mockResolvedValue(snapshot(0, item(1)));
  const e = f.make();
  e.activate('A');
  await e.flush();
  const latest = snapshot(2, item(5), item(6, 2));
  f.write
    .mockRejectedValueOnce({ status: 409, payload: { cart: latest }, message: 'conflict' })
    .mockResolvedValueOnce(snapshot(3, item(3), item(6, 2)));
  e.edit([item(3)]);
  await expect(e.flush()).rejects.toThrow();
  expect(e.items).toEqual([item(3)]);
  expect(e.status).toBe('conflict');
  e.resolve(true);
  await e.flush();
  expect(e.items).toEqual([item(3), item(6, 2)]);
  expect(f.write.mock.calls[1][0].changes).toEqual([
    { product_id: 1, expected_quantity: '5.000', quantity: '3.000' },
  ]);
});
it('does not write on a failed load or import another account cache', async () => {
  const f = setup([item(2)]);
  f.read.mockRejectedValueOnce(new Error('offline'));
  const e = f.make();
  e.activate('A');
  await expect(e.flush()).rejects.toThrow();
  expect(e.items).toEqual([item(2)]);
  expect(f.write).not.toHaveBeenCalled();
  f.read.mockResolvedValue(snapshot(0));
  f.write.mockResolvedValue(snapshot(1, item(2)));
  await e.flush();
  e.activate('B');
  await e.flush();
  expect(e.items).toEqual([]);
  expect(f.write).toHaveBeenCalledTimes(1);
});
it('keeps post-order recovery through a failed GET and restart, instead of importing the old cart', async () => {
  const f = setup();
  f.read.mockResolvedValue(snapshot(1, item(2)));
  const e = f.make();
  e.activate('A');
  await e.flush();
  f.read.mockRejectedValueOnce(new Error('offline'));
  e.orderSaved([item(2)]);
  await expect(e.flush()).rejects.toThrow();
  expect(e.items).toEqual([]);
  e.dispose();
  f.read.mockResolvedValue(snapshot(2, item(5, 2)));
  const reopened = f.make();
  reopened.activate('A');
  await reopened.flush();
  expect(reopened.items).toEqual(cartItems(snapshot(2, item(5, 2))));
  expect(f.write).not.toHaveBeenCalled();
});

it('does not apply an older in-flight cart response after order confirmation', async () => {
  const f = setup();
  f.read.mockResolvedValue(snapshot(1, item(2), item(1, 2)));
  const e = f.make();
  e.activate('A');
  await e.flush();
  let finish!: (v: ServerCart) => void;
  f.write.mockImplementationOnce(
    () =>
      new Promise<ServerCart>((resolve) => {
        finish = resolve;
      }),
  );
  e.edit([item(3), item(1, 2)]);
  const old = e.sync();
  f.read.mockResolvedValue(snapshot(3, item(3)));
  e.orderSaved([item(2), item(1, 2)]);
  finish(snapshot(2, item(3), item(1, 2)));
  await old;
  await e.flush();
  expect(e.items).toEqual([item(3)]);
  expect(e.afterOrder).toBe(false);
  expect(e.status).toBe('synced');
  expect(f.write).toHaveBeenCalledTimes(1);
});
