import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchProducts, fetchProductPage } from '../lib/api';
import { loadProductSnapshot } from './useCatalog';
import type { Product } from '../types';

vi.mock('../lib/api', () => ({
  fetchProducts: vi.fn(),
  fetchProductPage: vi.fn(),
  fetchCategories: vi.fn(),
  fetchProduct: vi.fn(),
}));
const product = (id: number, price = '100.00') => ({ id, price }) as Product;
beforeEach(() => vi.resetAllMocks());

describe('catalog background revalidation', () => {
  it('refreshes all loaded pages with current prices and availability without dropping list depth', async () => {
    const signal = new AbortController().signal;
    vi.mocked(fetchProducts).mockResolvedValue({
      count: 3,
      next: '/api/products/?page=2',
      previous: null,
      results: [product(1, '120.00')],
    });
    vi.mocked(fetchProductPage).mockResolvedValue({
      count: 3,
      next: '/api/products/?page=3',
      previous: null,
      results: [{ ...product(2), is_available: false }],
    });
    const result = await loadProductSnapshot({ category: 'beef' }, 2, signal);
    expect(fetchProducts).toHaveBeenCalledWith({ category: 'beef' }, signal);
    expect(result).toMatchObject({ pages: 2, next: '/api/products/?page=3', count: 3 });
    expect(result.products.map((item) => item.id)).toEqual([1, 2]);
    expect(result.validated[0].price).toBe('120.00');
    expect(result.validated[1].is_available).toBe(false);
  });

  it('handles a smaller catalog and never requests a missing next page', async () => {
    vi.mocked(fetchProducts).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [product(1)],
    });
    const result = await loadProductSnapshot({}, 4, new AbortController().signal);
    expect(result.pages).toBe(1);
    expect(result.next).toBeNull();
    expect(fetchProductPage).not.toHaveBeenCalled();
  });

  it('does not publish a partially revalidated list if a later page fails', async () => {
    vi.mocked(fetchProducts).mockResolvedValue({
      count: 2,
      next: '/api/products/?page=2',
      previous: null,
      results: [product(1)],
    });
    vi.mocked(fetchProductPage).mockRejectedValue(new Error('Offline'));
    await expect(loadProductSnapshot({}, 2, new AbortController().signal)).rejects.toThrow(
      'Offline'
    );
  });
});
