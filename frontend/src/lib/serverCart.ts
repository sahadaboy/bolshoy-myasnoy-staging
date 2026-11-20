import type { CartItem, Product } from '../types';
import { get } from './api';
export interface ServerCart {
  revision: number;
  items: { product_id: number; product: Product | null; quantity: string }[];
}
export interface CartMutation {
  operation_id: string;
  base_revision: number;
  mode: 'patch' | 'merge';
  changes: { product_id: number; quantity: string; expected_quantity: string }[];
}
export const readServerCart = () => get<ServerCart>('/api/cart/');
export const writeServerCart = (body: CartMutation) =>
  get<ServerCart>('/api/cart/', undefined, false, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
export function cartItems(cart: ServerCart): CartItem[] {
  return cart.items.map((line) => ({
    quantity: Math.round(Number(line.quantity) * 1000),
    product: line.product || {
      id: line.product_id,
      name: `Товар №${line.product_id} больше недоступен`,
      sku: '',
      price: '0.00',
      unit: 'pcs',
      min_quantity: '1.000',
      quantity_step: '1.000',
      description: 'Удалён из каталога',
      image: null,
      is_available: false,
      categories: [],
    },
  }));
}
const q = (n: number) => `${Math.floor(n / 1000)}.${String(n % 1000).padStart(3, '0')}`;
export function changes(before: CartItem[], after: CartItem[]) {
  const old = new Map(before.map((i) => [i.product.id, i.quantity]));
  const next = new Map(after.map((i) => [i.product.id, i.quantity]));
  return [...new Set([...old.keys(), ...next.keys()])]
    .filter((id) => (old.get(id) || 0) !== (next.get(id) || 0))
    .map((id) => ({
      product_id: id,
      quantity: q(next.get(id) || 0),
      expected_quantity: q(old.get(id) || 0),
    }));
}
export function overlay(server: CartItem[], before: CartItem[], after: CartItem[]) {
  const result = new Map(server.map((i) => [i.product.id, i]));
  for (const change of changes(before, after)) {
    const item = after.find((i) => i.product.id === change.product_id);
    if (item) result.set(change.product_id, item);
    else result.delete(change.product_id);
  }
  return [...result.values()];
}
