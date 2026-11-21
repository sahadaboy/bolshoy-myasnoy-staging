import { afterEach, describe, expect, it, vi } from 'vitest';
import { initializeScrollMemory } from './ScrollMemory';
import { NavigationMemory } from '../lib/navigationMemory';

afterEach(() => vi.unstubAllGlobals());
const catalog = { pathname: '/catalog', search: '?all=1', key: 'c1' };
function viewport(maximum: number) {
  let y = 0;
  let max = maximum;
  const listeners = new Map<string, (event?: unknown) => void>();
  const frames = new Map<number, () => void>();
  const observers: { run: () => void; disconnect: ReturnType<typeof vi.fn> }[] = [];
  const browser = {
    history: { scrollRestoration: 'auto' },
    get scrollY() {
      return y;
    },
    scrollTo: vi.fn(({ top }: { top: number }) => {
      y = Math.min(max, top);
    }),
    addEventListener: vi.fn((name: string, listener: (event?: unknown) => void) =>
      listeners.set(name, listener)
    ),
    removeEventListener: vi.fn((name: string) => listeners.delete(name)),
  };
  vi.stubGlobal('window', browser);
  vi.stubGlobal('document', { getElementById: () => ({}) });
  vi.stubGlobal('requestAnimationFrame', (callback: () => void) => {
    frames.set(1, callback);
    return 1;
  });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id));
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe = vi.fn();
      disconnect = vi.fn();
      constructor(run: () => void) {
        observers.push({ run, disconnect: this.disconnect });
      }
    }
  );
  return {
    browser,
    listeners,
    observers,
    grow: (height: number) => {
      max = height;
    },
    scroll: (position: number) => {
      y = position;
      listeners.get('scroll')?.();
    },
    flush: () => {
      const pending = [...frames.values()];
      frames.clear();
      pending.forEach((run) => run());
    },
  };
}

describe('scroll restoration without browser automation', () => {
  it('restores a cached tab synchronously and cleans up history/listeners', () => {
    const v = viewport(2000);
    const memory = new NavigationMemory();
    memory.save(catalog, 700);
    const cleanup = initializeScrollMemory({ ...catalog, key: 'c2' }, 'PUSH', memory);
    expect(v.browser.scrollY).toBe(700);
    expect(v.observers).toHaveLength(0);
    expect(v.browser.history.scrollRestoration).toBe('manual');
    v.scroll(900);
    cleanup();
    expect(memory.enter({ ...catalog, key: 'c3' }, 'PUSH')).toBe(900);
    expect(v.listeners.size).toBe(0);
    expect(v.browser.history.scrollRestoration).toBe('auto');
  });

  it('waits for an uncached page to grow instead of losing the saved position to a skeleton', () => {
    const v = viewport(200);
    const memory = new NavigationMemory();
    memory.save(catalog, 1200);
    const cleanup = initializeScrollMemory({ ...catalog, key: 'c2' }, 'PUSH', memory);
    v.grow(1800);
    v.observers[0].run();
    v.flush();
    expect(v.browser.scrollY).toBe(1200);
    expect(v.observers[0].disconnect).toHaveBeenCalled();
    cleanup();
  });

  it('never forces an old position after the user starts interacting', () => {
    const v = viewport(200);
    const memory = new NavigationMemory();
    memory.save(catalog, 1200);
    const cleanup = initializeScrollMemory({ ...catalog, key: 'c2' }, 'PUSH', memory);
    v.listeners.get('pointerdown')?.();
    v.scroll(150);
    v.grow(1800);
    v.observers[0].run();
    v.flush();
    expect(v.browser.scrollY).toBe(150);
    cleanup();
    expect(memory.enter({ ...catalog, key: 'c3' }, 'PUSH')).toBe(150);
  });
});
