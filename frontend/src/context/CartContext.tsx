import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import type { CartItem, Product } from '../types';
import { useSession } from './SessionContext';
import { CartSync, type CartViewState } from '../lib/cartSync';
import { readServerCart, writeServerCart } from '../lib/serverCart';
import {
  addQuantities,
  lineTotal,
  minQuantity,
  normalizeQuantity,
  stepQuantity,
} from '../lib/quantity';

const STORAGE_KEY = 'bolshoy-myasnoy.cart.v1';
const MAX_STORED_ITEMS = 6000;

interface CartContextValue {
  localChangeId: number;
  syncStatus: CartViewState['status'];
  syncError: string;
  retrySync: () => void;
  resolveSync: (mine: boolean) => void;
  flush: () => Promise<CartItem[]>;
  orderSaved: (submitted: CartItem[]) => void;
  items: CartItem[];
  add: (product: Product, quantity?: number) => boolean;
  addMany: (items: CartItem[]) => boolean;
  setQuantity: (product: Product, quantity: number) => boolean;
  increase: (product: Product) => boolean;
  decrease: (product: Product) => boolean;
  remove: (id: number) => void;
  clear: () => void;
  getQuantity: (id: number) => number;
  syncProducts: (products: Product[]) => void;
  totalKopecks: number;
  itemCount: number;
  storageIssue: boolean;
}

const CartContext = createContext<CartContextValue | null>(null);

function isProduct(value: unknown): value is Product {
  if (!value || typeof value !== 'object') return false;
  const product = value as Record<string, unknown>;
  return (
    Number.isSafeInteger(product.id) &&
    Number(product.id) > 0 &&
    typeof product.name === 'string' &&
    typeof product.sku === 'string' &&
    typeof product.price === 'string' &&
    /^\d+(?:\.\d{1,2})?$/.test(product.price) &&
    (product.unit === 'kg' || product.unit === 'pcs') &&
    typeof product.min_quantity === 'string' &&
    /^\d+(?:\.\d{1,3})?$/.test(product.min_quantity) &&
    typeof product.quantity_step === 'string' &&
    /^\d+(?:\.\d{1,3})?$/.test(product.quantity_step) &&
    typeof product.description === 'string' &&
    (product.image === null || typeof product.image === 'string') &&
    typeof product.is_available === 'boolean' &&
    Array.isArray(product.categories) &&
    product.categories.every((category: unknown) => {
      if (!category || typeof category !== 'object') return false;
      const candidate = category as Record<string, unknown>;
      return Number.isSafeInteger(candidate.id) && typeof candidate.name === 'string';
    })
  );
}

function total(items: CartItem[]): number {
  return items.reduce(
    (sum, item) => sum + (item.product.is_available ? lineTotal(item.product, item.quantity) : 0),
    0,
  );
}

function loadCart(): { items: CartItem[]; storageIssue: boolean } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { items: [], storageIssue: false };
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return { items: [], storageIssue: true };
    const items: CartItem[] = [];
    const ids = new Set<number>();
    for (const value of parsed.slice(0, MAX_STORED_ITEMS)) {
      if (!value || typeof value !== 'object') continue;
      const candidate = value as Record<string, unknown>;
      if (!isProduct(candidate.product) || !Number.isSafeInteger(candidate.quantity)) continue;
      const quantity = normalizeQuantity(candidate.product, Number(candidate.quantity));
      if (!quantity || ids.has(candidate.product.id)) continue;
      const item = { product: candidate.product, quantity };
      if (!Number.isSafeInteger(total([...items, item]))) continue;
      items.push(item);
      ids.add(candidate.product.id);
    }
    return { items, storageIssue: false };
  } catch {
    return { items: [], storageIssue: true };
  }
}

export function CartProvider({ children }: { children: ReactNode }) {
  const [localChangeId, setLocalChangeId] = useState(0);
  const session = useSession();
  const [initial] = useState(loadCart);
  const [items, setItems] = useState<CartItem[]>(initial.items);
  const [storageIssue, setStorageIssue] = useState(initial.storageIssue);
  const itemsRef = useRef(items);
  const [syncState, setSyncState] = useState<Pick<CartViewState, 'status' | 'error'>>({
    status: 'loading',
    error: '',
  });
  const [engine] = useState(
    () =>
      new CartSync(
        {
          getItem: (key) => localStorage.getItem(key),
          setItem: (key, value) => localStorage.setItem(key, value),
          removeItem: (key) => localStorage.removeItem(key),
        },
        (raw) =>
          Array.isArray(raw)
            ? raw.filter(
                (item) =>
                  item &&
                  isProduct(item.product) &&
                  Number.isSafeInteger(item.quantity) &&
                  item.quantity > 0,
              )
            : [],
        readServerCart,
        writeServerCart,
        (view) => {
          itemsRef.current = view.items;
          setItems(view.items);
          setSyncState({ status: view.status, error: view.error });
        },
        () => setStorageIssue(true),
      ),
  );
  const owner = session.data?.authenticated ? session.data.user?.id : undefined;
  useEffect(() => {
    if (owner) engine.activate(owner);
    else if (session.data && !session.data.authenticated) engine.activate('guest');
    else if (session.error) engine.pause(session.authenticationRequired);
  }, [owner, session.data?.authenticated, session.error, session.authenticationRequired, engine]);
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === 'visible') void engine.sync();
    };
    const timer = setInterval(refresh, 5000);
    window.addEventListener('focus', refresh);
    window.addEventListener('online', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      clearInterval(timer);
      window.removeEventListener('focus', refresh);
      window.removeEventListener('online', refresh);
      document.removeEventListener('visibilitychange', refresh);
      engine.dispose();
    };
  }, [engine]);

  const commit = useCallback(
    (next: CartItem[]): boolean => {
      if (!Number.isSafeInteger(total(next))) return false;
      if (next.length !== itemsRef.current.length) setLocalChangeId((value) => value + 1);
      itemsRef.current = next;
      setItems(next);
      engine.edit(next);
      return true;
    },
    [engine],
  );

  const setQuantity = useCallback(
    (product: Product, requested: number): boolean => {
      const current = itemsRef.current;
      const existing = current.find((item) => item.product.id === product.id);
      if (requested === 0) return commit(current.filter((item) => item.product.id !== product.id));
      if (!product.is_available && (!existing || requested > existing.quantity)) return false;
      const quantity = normalizeQuantity(product, requested);
      if (!quantity) return false;
      const next = existing
        ? current.map((item) => (item.product.id === product.id ? { product, quantity } : item))
        : [...current, { product, quantity }];
      return commit(next);
    },
    [commit],
  );

  const add = useCallback(
    (product: Product, quantity = minQuantity(product)): boolean => {
      if (!product.is_available || !quantity) return false;
      const existing = itemsRef.current.find((item) => item.product.id === product.id);
      const combined = addQuantities(product, existing?.quantity ?? 0, quantity);
      return combined > 0 && setQuantity(product, combined);
    },
    [setQuantity],
  );

  const increase = useCallback(
    (product: Product): boolean => {
      if (!product.is_available) return false;
      const existing = itemsRef.current.find((item) => item.product.id === product.id);
      return setQuantity(
        product,
        existing ? existing.quantity + stepQuantity(product) : minQuantity(product),
      );
    },
    [setQuantity],
  );

  const addMany = useCallback(
    (incoming: CartItem[]): boolean => {
      const next = [...itemsRef.current];
      for (const item of incoming) {
        if (!item.product.is_available || !item.quantity) return false;
        const index = next.findIndex((existing) => existing.product.id === item.product.id);
        const quantity = addQuantities(
          item.product,
          index >= 0 ? next[index].quantity : 0,
          item.quantity,
        );
        if (!quantity) return false;
        if (index >= 0) next[index] = { product: item.product, quantity };
        else next.push({ product: item.product, quantity });
      }
      return incoming.length > 0 && commit(next);
    },
    [commit],
  );

  const decrease = useCallback(
    (product: Product): boolean => {
      const existing = itemsRef.current.find((item) => item.product.id === product.id);
      if (!existing) return false;
      const quantity = existing.quantity - stepQuantity(product);
      return setQuantity(product, quantity < minQuantity(product) ? 0 : quantity);
    },
    [setQuantity],
  );

  const remove = useCallback(
    (id: number) => {
      commit(itemsRef.current.filter((item) => item.product.id !== id));
    },
    [commit],
  );

  const clear = useCallback(() => {
    commit([]);
  }, [commit]);
  const getQuantity = useCallback(
    (id: number) => itemsRef.current.find((item) => item.product.id === id)?.quantity ?? 0,
    [],
  );

  const syncProducts = useCallback(
    (products: Product[]) => {
      const latest = new Map(products.map((product) => [product.id, product]));
      let changed = false;
      const next: CartItem[] = [];
      for (const item of itemsRef.current) {
        const product = latest.get(item.product.id);
        if (!product) {
          next.push(item);
          continue;
        }
        const quantity = item.quantity;
        const currentProduct =
          normalizeQuantity(product, quantity) === quantity
            ? product
            : { ...product, is_available: false };
        if (
          quantity !== item.quantity ||
          JSON.stringify(currentProduct) !== JSON.stringify(item.product)
        ) {
          changed = true;
          next.push({ product: currentProduct, quantity });
        } else next.push(item);
      }
      if (changed) engine.metadata(next);
    },
    [engine],
  );

  return (
    <CartContext.Provider
      value={{
        localChangeId,
        syncStatus: syncState.status,
        syncError: syncState.error,
        retrySync: () => void engine.sync(),
        resolveSync: (mine) => engine.resolve(mine),
        flush: () => engine.flush(),
        orderSaved: (submitted) => engine.orderSaved(submitted),
        items,
        add,
        addMany,
        setQuantity,
        increase,
        decrease,
        remove,
        clear,
        getQuantity,
        syncProducts,
        totalKopecks: total(items),
        itemCount: items.length,
        storageIssue,
      }}
    >
      {children}
    </CartContext.Provider>
  );
}

export function useCart(): CartContextValue {
  const context = useContext(CartContext);
  if (!context) throw new Error('useCart must be used inside CartProvider');
  return context;
}
