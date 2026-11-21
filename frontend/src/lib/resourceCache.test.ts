import { afterEach, describe, expect, it, vi } from 'vitest';
import { ResourceCache, ResourceEntry } from './resourceCache';

afterEach(() => vi.useRealTimers());
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe('shared resource cache', () => {
  it('deduplicates a pending request and retains it after the last page unmounts', async () => {
    const cache = new ResourceCache();
    const entry = cache.get<number>('storefront');
    const pending = deferred<number>();
    const load = vi.fn(() => pending.promise);
    const unsubscribe = entry.subscribe(vi.fn());
    const first = entry.load(load);
    unsubscribe();
    const returning = cache.get<number>('storefront');
    expect(returning).toBe(entry);
    expect(returning.load(load)).toBe(first);
    pending.resolve(42);
    await first;
    expect(load).toHaveBeenCalledTimes(1);
    expect(returning.getSnapshot().data).toBe(42);
  });

  it('returns fresh cached data without a new request, then refreshes stale data in place', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(1000);
    const entry = new ResourceEntry<number>();
    await entry.load(async () => 10);
    const revision = entry.getSnapshot().revision;
    const load = vi.fn(async () => 20);
    await entry.load(load, { staleTime: 15_000 });
    expect(load).not.toHaveBeenCalled();
    expect(entry.getSnapshot().revision).toBe(revision);
    vi.advanceTimersByTime(15_001);
    const update = entry.load(load, { staleTime: 15_000 });
    expect(entry.getSnapshot()).toMatchObject({ data: 10, refreshing: true });
    await update;
    expect(entry.getSnapshot()).toMatchObject({
      data: 20,
      refreshing: false,
      revision: revision + 1,
    });
  });

  it('retains content on a failed refresh and allows an immediate forced retry', async () => {
    const entry = new ResourceEntry<number>();
    await entry.load(async () => 10);
    await expect(
      entry.load(async () => {
        throw new Error('Offline');
      })
    ).rejects.toThrow('Offline');
    expect(entry.getSnapshot()).toMatchObject({ data: 10, error: 'Offline', refreshing: false });
    await entry.load(async () => 12, { force: true });
    expect(entry.getSnapshot()).toMatchObject({ data: 12, error: null });
  });

  it('does not make old product pages fresh merely because another page was appended', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(1000);
    const entry = new ResourceEntry<number[]>();
    await entry.load(async () => [1]);
    vi.advanceTimersByTime(20_000);
    await entry.load(async () => [1, 2], { force: true, preserveAge: true });
    expect(entry.getSnapshot().updatedAt).toBe(1000);
    const refresh = vi.fn(async () => [3, 4]);
    await entry.load(refresh, { staleTime: 15_000 });
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('isolates accounts and removes cached private data on authentication failure', async () => {
    const cache = new ResourceCache();
    const first = cache.get<string>('profile-orders:1');
    await first.load(async () => 'private');
    expect(cache.get<string>('profile-orders:2').getSnapshot().data).toBeUndefined();
    await expect(
      first.load(async () => {
        throw Object.assign(new Error('Sign in'), { status: 401 });
      })
    ).rejects.toThrow('Sign in');
    expect(first.getSnapshot().data).toBeUndefined();
  });

  it('evicts inactive least recently used entries while protecting subscribers and requests', async () => {
    const cache = new ResourceCache(2);
    const active = cache.get('active');
    const unsubscribe = active.subscribe(vi.fn());
    const old = cache.get('old');
    const pending = cache.get<number>('pending');
    const deferredLoad = deferred<number>();
    const request = pending.load(() => deferredLoad.promise);
    expect(cache.get('active')).toBe(active);
    expect(cache.get('old')).not.toBe(old);
    expect(cache.get('pending')).toBe(pending);
    deferredLoad.resolve(1);
    await request;
    unsubscribe();
  });

  it('ignores a canceled response even if the loader does not honor AbortSignal', async () => {
    const entry = new ResourceEntry<number>();
    const late = deferred<number>();
    const first = entry.load(() => late.promise);
    entry.cancel();
    await entry.load(async () => 2);
    late.resolve(1);
    await first;
    expect(entry.getSnapshot().data).toBe(2);
  });

  it('bounds retention again after a burst of pending requests finishes', async () => {
    const cache = new ResourceCache(2);
    const jobs = [0, 1, 2, 3].map((id) => cache.get<number>(String(id)).load(async () => id));
    await Promise.all(jobs);
    expect(cache.get<number>('0').getSnapshot().data).toBeUndefined();
    expect(cache.get<number>('3').getSnapshot().data).toBe(3);
  });
});
