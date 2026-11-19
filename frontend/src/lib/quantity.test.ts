import { describe, expect, it } from 'vitest';
import type { Product } from '../types';
import {
  addQuantities,
  formatMoney,
  formatQuantity,
  lineTotal,
  minQuantity,
  normalizeQuantity,
  priceKopecks,
  stepQuantity,
} from './quantity';

const product: Product = {
  id: 1,
  name: 'Товар',
  sku: '1',
  price: '159.99',
  unit: 'kg',
  min_quantity: '0.300',
  quantity_step: '0.100',
  description: '',
  image: null,
  categories: [],
  is_available: true,
};

describe('Decimal-compatible quantity and money arithmetic', () => {
  it('never silently reduces a repeated addition when the minimum is not a step multiple', () => {
    const quarter = { ...product, min_quantity: '0.250', quantity_step: '0.100' };
    expect(addQuantities(quarter, 0, 250)).toBe(250);
    expect(addQuantities(quarter, 250, 250)).toBe(0);
    expect(normalizeQuantity(quarter, 350)).toBe(350);
    expect(addQuantities(product, 300, 300)).toBe(600);
    expect(addQuantities(product, 300, 0)).toBe(0);
    expect(addQuantities(product, 300, Number.MAX_SAFE_INTEGER)).toBe(0);
  });
  it('parses API prices exactly and rounds line totals half up', () => {
    expect(priceKopecks(product)).toBe(15999);
    expect(lineTotal(product, 300)).toBe(4800);
    expect(lineTotal({ price: '0.05' }, 100)).toBe(1);
    expect(lineTotal({ price: '0.04' }, 100)).toBe(0);
  });

  it('repeats weight increments without accumulating floating-point error', () => {
    let quantity = minQuantity(product);
    for (let index = 0; index < 100; index += 1) quantity += stepQuantity(product);
    expect(quantity).toBe(10300);
    expect(lineTotal(product, quantity)).toBe(164790);
    for (let index = 0; index < 100; index += 1) quantity -= stepQuantity(product);
    expect(quantity).toBe(300);
  });

  it('uses the minimum as the origin of the API step lattice', () => {
    const custom = { ...product, min_quantity: '0.250', quantity_step: '0.100' };
    expect(normalizeQuantity(custom, 100)).toBe(250);
    expect(normalizeQuantity(custom, 440)).toBe(350);
    expect(normalizeQuantity(custom, 450)).toBe(450);
    expect(normalizeQuantity(custom, 0)).toBe(0);
  });

  it('keeps pcs integer while respecting both minimum and step', () => {
    const pieces: Product = {
      ...product,
      unit: 'pcs',
      min_quantity: '2.000',
      quantity_step: '3.000',
    };
    expect(minQuantity(pieces)).toBe(2000);
    expect(stepQuantity(pieces)).toBe(3000);
    expect(normalizeQuantity(pieces, 7000)).toBe(5000);
    const fractional: Product = { ...pieces, min_quantity: '1.200', quantity_step: '0.300' };
    expect(minQuantity(fractional)).toBe(3000);
    expect(stepQuantity(fractional)).toBe(3000);
    expect(normalizeQuantity(fractional, 7000)).toBe(6000);
  });

  it('rejects an impossible integer piece lattice and invalid quantities', () => {
    const impossible: Product = {
      ...product,
      unit: 'pcs',
      min_quantity: '0.001',
      quantity_step: '1.000',
    };
    expect(minQuantity(impossible)).toBe(0);
    expect(normalizeQuantity(impossible, 1000)).toBe(0);
    expect(normalizeQuantity(product, Number.NaN)).toBe(0);
    expect(normalizeQuantity(product, 0.3)).toBe(0);
    expect(normalizeQuantity({ ...product, quantity_step: '0' }, 1000)).toBe(0);
  });

  it('formats Russian quantities and exact integer kopecks', () => {
    expect(formatQuantity(1250, 'kg')).toBe('1,25 кг');
    expect(formatQuantity(2000, 'pcs')).toBe('2 шт');
    expect(formatMoney(15999)).toBe('159,99 ₽');
    expect(formatMoney(10000)).toBe('100 ₽');
  });
});
