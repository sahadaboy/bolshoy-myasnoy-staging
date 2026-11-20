import { describe, expect, it, vi } from 'vitest';
import { completeBoot } from './boot';

function fixture(telegram = false, reduced = false) {
  const boot = {
    remove: vi.fn(),
    dataset: {} as Record<string, string>,
    addEventListener: vi.fn(),
  };
  const document = { getElementById: () => boot } as unknown as Document;
  const browser = {
    Telegram: telegram ? { WebApp: { platform: 'ios', ready: vi.fn() } } : undefined,
    matchMedia: () => ({ matches: reduced }),
    setTimeout: vi.fn(),
  } as unknown as Window;
  return { boot, document, browser };
}
describe('first shell splash readiness', () => {
  it('removes the custom splash before native Telegram ready, without waiting for API', () => {
    const f = fixture(true);
    completeBoot(f.document, f.browser);
    expect(f.boot.remove).toHaveBeenCalledOnce();
    expect(f.browser.Telegram!.WebApp!.ready).not.toHaveBeenCalled();
    expect(f.browser.setTimeout).not.toHaveBeenCalled();
  });
  it('makes the browser shell immediately interactive and removes the fade on completion', () => {
    const f = fixture();
    completeBoot(f.document, f.browser);
    expect(f.boot.dataset.ready).toBe('true');
    expect(f.boot.remove).not.toHaveBeenCalled();
    vi.mocked(f.boot.addEventListener).mock.calls[0][1]();
    expect(f.boot.remove).toHaveBeenCalledOnce();
  });
  it('skips transitions for reduced motion', () => {
    const f = fixture(false, true);
    completeBoot(f.document, f.browser);
    expect(f.boot.remove).toHaveBeenCalledOnce();
  });
  it('does not recreate splash on route changes or subsequent mounts', () => {
    const f = fixture();
    const document = { getElementById: () => null } as unknown as Document;
    expect(() => completeBoot(document, f.browser)).not.toThrow();
    expect(f.browser.setTimeout).not.toHaveBeenCalled();
  });
});
