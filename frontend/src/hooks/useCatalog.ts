import { useCallback, useEffect, useState } from 'react';
import type { Product, CatalogTag } from '../types';
import {
  fetchCategories,
  fetchProduct,
  fetchProductPage,
  fetchProducts,
  type ProductFilters,
} from '../lib/api';
import { resourceCache } from '../lib/resourceCache';
import { useResource } from './useResource';

const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : 'Не удалось загрузить данные.';
const emptyProducts: Product[] = [];

export function useCategories() {
  const resource = useResource(fetchCategories, { cacheKey: 'categories' });
  return { ...resource, categories: resource.data || [] };
}

type ProductSnapshot = {
  products: Product[];
  count: number;
  next: string | null;
  tags: CatalogTag[];
  pages: number;
  validated: Product[];
};
const uniqueProducts = (products: Product[]) => [
  ...new Map(products.map((product) => [product.id, product])).values(),
];

/** Refresh the loaded depth atomically: never collapse a scrolled list to page one. */
export async function loadProductSnapshot(
  filters: ProductFilters,
  depth: number,
  signal: AbortSignal
): Promise<ProductSnapshot> {
  let page = await fetchProducts(filters, signal);
  const count = page.count;
  const tags = page.tags || [];
  const products = [...page.results];
  const seen = new Set<string>();
  let pages = 1;
  while (page.next && pages < depth) {
    if (seen.has(page.next)) throw new Error('Сервер повторяет страницу товаров.');
    seen.add(page.next);
    page = await fetchProductPage(page.next, signal);
    products.push(...page.results);
    pages += 1;
  }
  const unique = uniqueProducts(products);
  return { products: unique, count, tags, next: page.next, pages, validated: unique };
}

export function useProducts(
  {
    category,
    categoryGroup,
    tag,
    search,
    unit,
    available,
    ordering,
    collection,
  }: ProductFilters = {},
  enabled = true
) {
  const cacheKey =
    'products:' +
    JSON.stringify([
      category || '',
      categoryGroup || '',
      tag || '',
      search || '',
      unit || '',
      !!available,
      ordering || '',
      collection || '',
    ]);
  const load = useCallback(
    (signal: AbortSignal) =>
      loadProductSnapshot(
        { category, categoryGroup, tag, search, unit, available, ordering, collection },
        resourceCache.get<ProductSnapshot>(cacheKey).getSnapshot().data?.pages || 1,
        signal
      ),
    [category, categoryGroup, tag, search, unit, available, ordering, collection, cacheKey]
  );
  const resource = useResource(load, {
    cacheKey,
    staleTime: 15_000,
    refreshInterval: 30_000,
    enabled,
  });
  const { entry } = resource;
  const [moreKey, setMoreKey] = useState<string | null>(null);
  const loadMore = useCallback(async () => {
    const current = entry.getSnapshot();
    if (!enabled || current.refreshing || !current.data?.next) return;
    const previous = current.data;
    setMoreKey(cacheKey);
    try {
      await entry.load(
        async (signal) => {
          const page = await fetchProductPage(previous.next!, signal);
          return {
            products: uniqueProducts([...previous.products, ...page.results]),
            count: page.count,
            next: page.next,
            tags: page.tags || previous.tags,
            pages: previous.pages + 1,
            validated: page.results,
          };
        },
        { force: true, preserveAge: true }
      );
    } catch {
      // The shared entry retains the list and exposes a retryable error.
    } finally {
      setMoreKey((key) => (key === cacheKey ? null : key));
    }
  }, [entry, enabled, cacheKey]);
  return {
    products: resource.data?.products || emptyProducts,
    validatedProducts: resource.revalidated ? resource.data!.validated : emptyProducts,
    loading: resource.loading,
    loadingMore: moreKey === cacheKey,
    refreshing: resource.refreshing,
    error: resource.error || resource.refreshError,
    count: resource.data?.count || 0,
    tags: resource.data?.tags || [],
    next: resource.data?.next || null,
    hasMore: Boolean(resource.data?.next),
    loadMore,
    retry: resource.retry,
  };
}

export function useProduct(id: string | undefined) {
  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((value) => value + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    setProduct((previous) => (previous?.id === Number(id) ? previous : null));
    setLoading(true);
    setError(null);
    fetchProduct(id ?? '', controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setProduct(data);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(errorMessage(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [id, attempt]);

  return { product, loading, error, retry };
}
