import { useCallback, useEffect, useRef, useState } from 'react';
import type { Category, Product } from '../types';
import {
  fetchCategories,
  fetchProduct,
  fetchProductPage,
  fetchProducts,
  type ProductFilters,
} from '../lib/api';

const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : 'Не удалось загрузить данные.';

// A small shared resource avoids duplicate category requests across navigation
// and StrictMode mounts. Each subscriber still ignores updates after unmount.
let categoriesCache: { data: Category[]; expires: number } | undefined;
let categoriesRequest: Promise<Category[]> | undefined;
function loadCategories(force: boolean): Promise<Category[]> {
  if (!force && categoriesCache && categoriesCache.expires > Date.now())
    return Promise.resolve(categoriesCache.data);
  if (!categoriesRequest) {
    categoriesRequest = fetchCategories()
      .then((data) => {
        categoriesCache = { data, expires: Date.now() + 60_000 };
        return data;
      })
      .finally(() => {
        categoriesRequest = undefined;
      });
  }
  return categoriesRequest;
}

export function useCategories() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((value) => value + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    loadCategories(attempt > 0)
      .then((data) => {
        if (!controller.signal.aborted) setCategories(data);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(errorMessage(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [attempt]);

  return { categories, loading, error, retry };
}

type ProductSnapshot = { products: Product[]; count: number; next: string | null; expires: number };
const productSnapshots = new Map<string, ProductSnapshot>();
function rememberProducts(key: string, value: Omit<ProductSnapshot, 'expires'>) {
  productSnapshots.delete(key);
  productSnapshots.set(key, { ...value, expires: Date.now() + 300_000 });
  while (productSnapshots.size > 3) productSnapshots.delete(productSnapshots.keys().next().value!);
}

export function useProducts(
  { category, categoryGroup, search, unit, available, ordering, collection }: ProductFilters = {},
  enabled = true,
) {
  const cacheKey = JSON.stringify([
    category || '',
    categoryGroup || '',
    search || '',
    unit || '',
    !!available,
    ordering || '',
    collection || '',
  ]);
  const initial = productSnapshots.get(cacheKey);
  const [products, setProducts] = useState<Product[]>(initial?.products || []);
  const [loading, setLoading] = useState(enabled && !initial);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [count, setCount] = useState(initial?.count || 0);
  const [next, setNext] = useState<string | null>(initial?.next || null);
  const [attempt, setAttempt] = useState(0);
  const currentController = useRef<AbortController | null>(null);
  const busy = useRef(false);
  const retry = useCallback(() => setAttempt((value) => value + 1), []);

  useEffect(() => {
    currentController.current?.abort();
    const controller = new AbortController();
    currentController.current = controller;
    if (!enabled) {
      setLoading(false);
      busy.current = false;
      return () => controller.abort();
    }
    const cached = productSnapshots.get(cacheKey);
    if (attempt === 0 && cached && cached.expires > Date.now()) {
      setProducts(cached.products);
      setCount(cached.count);
      setNext(cached.next);
      setLoading(false);
      setLoadingMore(false);
      setError(null);
      busy.current = false;
      return () => controller.abort();
    }
    busy.current = true;
    setProducts([]);
    setNext(null);
    setCount(0);
    setLoading(true);
    setLoadingMore(false);
    setError(null);
    fetchProducts(
      { category, categoryGroup, search, unit, available, ordering, collection },
      controller.signal,
    )
      .then((page) => {
        if (controller.signal.aborted) return;
        setProducts(page.results);
        setCount(page.count);
        setNext(page.next);
        rememberProducts(cacheKey, { products: page.results, count: page.count, next: page.next });
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(errorMessage(reason));
      })
      .finally(() => {
        if (controller.signal.aborted) return;
        setLoading(false);
        busy.current = false;
      });
    return () => controller.abort();
  }, [
    category,
    categoryGroup,
    search,
    unit,
    available,
    ordering,
    collection,
    attempt,
    enabled,
    cacheKey,
  ]);

  const loadMore = useCallback(async () => {
    if (!next || busy.current) return;
    const controller = currentController.current;
    if (!controller || controller.signal.aborted) return;
    busy.current = true;
    setLoadingMore(true);
    setError(null);
    try {
      const page = await fetchProductPage(next, controller.signal);
      if (controller.signal.aborted) return;
      setProducts((previous) => {
        const combined = [
          ...new Map(
            [...previous, ...page.results].map((product) => [product.id, product]),
          ).values(),
        ];
        rememberProducts(cacheKey, { products: combined, count: page.count, next: page.next });
        return combined;
      });
      setCount(page.count);
      setNext(page.next);
    } catch (reason) {
      if (!controller.signal.aborted) setError(errorMessage(reason));
    } finally {
      if (!controller.signal.aborted) {
        busy.current = false;
        setLoadingMore(false);
      }
    }
  }, [next, cacheKey]);

  return {
    products,
    loading,
    loadingMore,
    error,
    count,
    next,
    hasMore: Boolean(next),
    loadMore,
    retry,
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
    setProduct(null);
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
