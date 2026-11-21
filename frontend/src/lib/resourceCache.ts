type Loader<T> = (signal: AbortSignal) => Promise<T>;
type Snapshot<T> = {
  data: T | undefined;
  error: string | null;
  refreshing: boolean;
  updatedAt: number;
  revision: number;
};

/** Memory only. Raw API calls (especially cart validation and orders) bypass this. */
export class ResourceEntry<T> {
  private snapshot: Snapshot<T> = {
    data: undefined,
    error: null,
    refreshing: false,
    updatedAt: 0,
    revision: 0,
  };
  private listeners = new Set<() => void>();
  private request?: Promise<T>;
  private controller?: AbortController;
  constructor(private onSettled?: () => void) {}
  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  get idle() {
    return !this.listeners.size && !this.request;
  }
  private publish(change: Partial<Snapshot<T>>) {
    this.snapshot = { ...this.snapshot, ...change };
    this.listeners.forEach((listener) => listener());
  }
  load(load: Loader<T>, { staleTime = 0, force = false, preserveAge = false } = {}): Promise<T> {
    if (this.request) return this.request;
    if (
      !force &&
      this.snapshot.data !== undefined &&
      Date.now() - this.snapshot.updatedAt < staleTime
    )
      return Promise.resolve(this.snapshot.data);
    const controller = new AbortController();
    this.controller = controller;
    this.publish({ refreshing: true, error: null });
    const request = Promise.resolve()
      .then(() => load(controller.signal))
      .then((data) => {
        if (this.controller === controller && !controller.signal.aborted) {
          this.publish({
            data,
            error: null,
            refreshing: false,
            updatedAt: preserveAge ? this.snapshot.updatedAt : Date.now(),
            revision: this.snapshot.revision + 1,
          });
        }
        return data;
      })
      .catch((reason: unknown) => {
        if (this.controller === controller && !controller.signal.aborted) {
          const status = (reason as { status?: number } | null)?.status;
          this.publish({
            ...(status === 401 || status === 403 ? { data: undefined, updatedAt: 0 } : {}),
            refreshing: false,
            error: reason instanceof Error ? reason.message : 'Не удалось загрузить данные.',
          });
        }
        throw reason;
      })
      .finally(() => {
        if (this.request === request) {
          this.request = undefined;
          this.onSettled?.();
        }
      });
    this.request = request;
    return request;
  }
  cancel() {
    this.controller?.abort();
    this.controller = undefined;
    this.request = undefined;
    this.publish({ refreshing: false });
  }
}

/** Bounded LRU; mounted resources and in-flight requests are never evicted. */
export class ResourceCache {
  private entries = new Map<string, ResourceEntry<unknown>>();
  constructor(private limit = 24) {}
  get<T>(key: string): ResourceEntry<T> {
    let entry = this.entries.get(key);
    if (!entry) entry = new ResourceEntry<unknown>(() => this.trim());
    this.entries.delete(key);
    this.entries.set(key, entry);
    this.trim(key);
    return entry as ResourceEntry<T>;
  }
  private trim(protectedKey?: string) {
    for (const [oldKey, old] of this.entries) {
      if (this.entries.size <= this.limit) break;
      if (oldKey !== protectedKey && old.idle) this.entries.delete(oldKey);
    }
  }
}

export const resourceCache = new ResourceCache();
