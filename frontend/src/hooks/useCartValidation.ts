import { useEffect, useRef, useState } from 'react';
import { useCart } from '../context/CartContext';
import { ApiError, fetchProduct } from '../lib/api';
import type { Product } from '../types';

export function useCartValidation() {
  const { items, syncProducts } = useCart();
  const current = useRef(items);
  current.current = items;
  const ids = items
    .map((item) => item.product.id)
    .sort((a, b) => a - b)
    .join(',');
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const queue = [...current.current];
    const updates: Product[] = [];
    let failed = false;
    setChecking(true);
    setError(false);
    async function worker() {
      while (queue.length && !controller.signal.aborted) {
        const item = queue.shift()!;
        try {
          updates.push(await fetchProduct(item.product.id, controller.signal));
        } catch (reason) {
          if (controller.signal.aborted) return;
          if (reason instanceof ApiError && reason.status === 404)
            updates.push({ ...item.product, is_available: false });
          else failed = true;
        }
      }
    }
    void Promise.all(Array.from({ length: Math.min(queue.length, 4) }, worker)).then(() => {
      if (!controller.signal.aborted) {
        syncProducts(updates);
        setError(failed);
        setChecking(false);
      }
    });
    return () => controller.abort();
  }, [ids, syncProducts, attempt]);
  return { checking, error, retry: () => setAttempt((value) => value + 1) };
}
