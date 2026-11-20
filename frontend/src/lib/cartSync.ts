import type { CartItem } from '../types';
import { cartItems, changes, overlay, type CartMutation, type ServerCart } from './serverCart';

export type CartSyncStatus =
  'guest' | 'loading' | 'synced' | 'saving' | 'offline' | 'conflict' | 'auth-required';
interface Pending {
  body: CartMutation;
  sent: CartItem[];
  imported: boolean;
}
interface Cache {
  base: ServerCart | null;
  items: CartItem[];
  pending: Pending | null;
  afterOrder: boolean;
}
export interface CartViewState {
  items: CartItem[];
  status: CartSyncStatus;
  error: string;
}
export class CartSync {
  owner: string | undefined;
  items: CartItem[];
  base: ServerCart | null = null;
  pending: Pending | null = null;
  afterOrder = false;
  conflict: ServerCart | null = null;
  status: CartSyncStatus = 'loading';
  error = '';
  private generation = 0;
  private flight: Promise<void> | null = null;
  private flightGeneration = 0;
  private active = true;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private extraGuest: CartItem[] = [];
  constructor(
    private storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>,
    private decode: (raw: unknown) => CartItem[],
    private read: () => Promise<ServerCart>,
    private write: (body: CartMutation) => Promise<ServerCart>,
    private emit: (value: CartViewState) => void,
    private storageFailed: () => void,
  ) {
    this.items = this.guest();
  }
  private guest() {
    try {
      return this.decode(JSON.parse(this.storage.getItem('bolshoy-myasnoy.cart.v1') || '[]'));
    } catch {
      return [];
    }
  }
  private key() {
    return `bm.server-cart.v1.${this.owner}`;
  }
  private persist() {
    try {
      if (!this.owner || this.owner === 'guest')
        this.storage.setItem('bolshoy-myasnoy.cart.v1', JSON.stringify(this.items));
      else
        this.storage.setItem(
          this.key(),
          JSON.stringify({
            base: this.base,
            items: this.items,
            pending: this.pending,
            afterOrder: this.afterOrder,
          }),
        );
    } catch {
      this.storageFailed();
    }
  }
  private publish() {
    this.emit({ items: this.items, status: this.status, error: this.error });
  }
  activate(owner: string) {
    this.active = true;
    if (owner === this.owner) {
      if (this.status === 'auth-required') this.status = 'loading';
      void this.sync();
      return;
    }
    if (owner === 'guest' && this.owner && this.owner !== 'guest') {
      this.pause();
      return;
    }
    this.generation++;
    this.owner = owner;
    this.conflict = null;
    this.pending = null;
    this.base = null;
    this.afterOrder = false;
    let cache: Cache | undefined;
    try {
      cache = JSON.parse(this.storage.getItem(this.key()) || 'null') || undefined;
    } catch {
      /* retain guest */
    }
    this.items = cache ? this.decode(cache.items) : this.guest();
    this.extraGuest = cache?.base ? this.guest() : [];
    if (
      cache &&
      cache.base &&
      Number.isSafeInteger(cache.base.revision) &&
      Array.isArray(cache.base.items)
    )
      this.base = cache.base;
    if (cache?.pending?.body && Array.isArray(cache.pending.sent)) this.pending = cache.pending;
    this.afterOrder = cache?.afterOrder === true;
    this.status = owner === 'guest' ? 'guest' : 'loading';
    this.publish();
    void this.sync();
  }
  pause(auth = true) {
    this.status = auth ? 'auth-required' : 'offline';
    this.publish();
  }
  edit(items: CartItem[]) {
    this.items = items;
    this.persist();
    if (
      this.owner &&
      this.owner !== 'guest' &&
      this.status !== 'conflict' &&
      this.status !== 'auth-required'
    ) {
      this.status = 'saving';
      clearTimeout(this.timer);
      this.timer = setTimeout(() => void this.sync(), 350);
    }
    this.publish();
  }
  metadata(items: CartItem[]) {
    this.items = items;
    this.persist();
    this.publish();
  }
  async sync(): Promise<void> {
    if (this.flight) {
      const generation = this.flightGeneration;
      await this.flight;
      if (this.active && generation !== this.generation) await this.sync();
      return;
    }
    if (!this.active) return;
    if (!this.owner || this.owner === 'guest' || this.status === 'auth-required' || this.conflict)
      return;
    const generation = this.generation;
    this.flightGeneration = generation;
    this.flight = this.run(generation).finally(() => {
      this.flight = null;
    });
    await this.flight;
  }
  private async run(generation: number) {
    this.error = '';
    this.status =
      this.base && (this.pending || changes(cartItems(this.base), this.items).length)
        ? 'saving'
        : this.status === 'synced'
          ? 'synced'
          : 'loading';
    this.publish();
    try {
      let fetched = false;
      if (!this.base) {
        const server = await this.read();
        if (generation !== this.generation) return;
        fetched = true;
        if (this.afterOrder) {
          this.items = overlay(cartItems(server), [], this.items);
          this.afterOrder = false;
          this.base = server;
        } else if (this.items.length) {
          this.pending = {
            body: {
              operation_id: crypto.randomUUID(),
              base_revision: server.revision,
              mode: 'merge',
              changes: changes([], this.items),
            },
            sent: this.items,
            imported: true,
          };
          this.base = server;
          this.persist();
        } else {
          this.base = server;
          this.items = cartItems(server);
        }
      }
      if (!this.pending && this.extraGuest.length) {
        this.pending = {
          body: {
            operation_id: crypto.randomUUID(),
            base_revision: this.base!.revision,
            mode: 'merge',
            changes: changes([], this.extraGuest),
          },
          sent: cartItems(this.base!),
          imported: true,
        };
      }
      if (!this.pending) {
        const diff = changes(cartItems(this.base!), this.items);
        if (diff.length)
          this.pending = {
            body: {
              operation_id: crypto.randomUUID(),
              base_revision: this.base!.revision,
              mode: 'patch',
              changes: diff,
            },
            sent: this.items,
            imported: false,
          };
      }
      if (this.pending) {
        const operation = this.pending;
        this.persist();
        const server = await this.write(operation.body);
        if (generation !== this.generation) return;
        if (operation.imported) {
          this.extraGuest = [];
          try {
            this.storage.removeItem('bolshoy-myasnoy.cart.v1');
          } catch {
            this.storageFailed();
          }
        }
        this.items = overlay(cartItems(server), operation.sent, this.items);
        this.base = server;
        this.pending = null;
      } else if (!fetched) {
        const before = this.items;
        const server = await this.read();
        if (generation !== this.generation) return;
        this.items = overlay(cartItems(server), before, this.items);
        this.base = server;
      }
      this.status = changes(cartItems(this.base!), this.items).length ? 'saving' : 'synced';
      this.persist();
      this.publish();
      if (this.status === 'saving') {
        clearTimeout(this.timer);
        this.timer = setTimeout(() => void this.sync(), 350);
      }
    } catch (reason) {
      if (generation !== this.generation) return;
      const error = reason as {
        status?: number;
        message?: string;
        payload?: { cart?: ServerCart };
      };
      if (error.status === 400 && this.pending) {
        if (this.pending.imported) {
          this.items = overlay(cartItems(this.base!), [], this.items);
          this.base = null;
          this.extraGuest = [];
        }
        this.pending = null;
      }
      if (error.status === 409 && error.payload?.cart) {
        this.conflict = error.payload.cart;
        this.status = 'conflict';
      } else this.status = error.status === 401 ? 'auth-required' : 'offline';
      this.error =
        error.message ||
        'Не удалось синхронизировать корзину. Выбранные товары сохранены на устройстве.';
      this.persist();
      this.publish();
    }
  }
  resolve(keepMine: boolean) {
    if (!this.conflict) return;
    this.items = keepMine
      ? overlay(cartItems(this.conflict), cartItems(this.base!), this.items)
      : cartItems(this.conflict);
    this.base = this.conflict;
    this.conflict = null;
    this.pending = null;
    this.status = 'saving';
    this.persist();
    void this.sync();
  }
  async flush() {
    clearTimeout(this.timer);
    for (let attempt = 0; attempt < 10; attempt++) {
      await this.sync();
      if (this.status === 'synced' || this.status === 'guest') return this.items;
      if (this.status !== 'saving' && this.status !== 'loading') break;
    }
    throw new Error(
      this.status === 'conflict'
        ? 'Сначала выберите, как объединить изменения корзины.'
        : 'Дождитесь синхронизации корзины и повторите оформление.',
    );
  }
  orderSaved(submitted: CartItem[]) {
    clearTimeout(this.timer);
    this.generation++;
    this.items = this.items.filter(
      (item) =>
        !submitted.some(
          (line) => line.product.id === item.product.id && line.quantity === item.quantity,
        ),
    );
    this.pending = null;
    this.base = null;
    this.afterOrder = true;
    this.status = 'loading';
    this.persist();
    this.publish();
    void this.sync();
  }
  dispose() {
    clearTimeout(this.timer);
    this.active = false;
    this.generation++;
  }
}
