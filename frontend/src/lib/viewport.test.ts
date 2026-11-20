import { describe, expect, it, vi } from 'vitest';
import { initializeVisualViewport } from './viewport';

function environment() {
  const values = new Map<string, string>();
  const viewport = Object.assign(new EventTarget(), { height: 844, offsetTop: 0, scale: 1 });
  const document = Object.assign(new EventTarget(), {
    activeElement: null as unknown,
    querySelector: vi.fn(() => null),
  });
  const browser = Object.assign(new EventTarget(), {
    visualViewport: viewport,
    innerHeight: 844,
    innerWidth: 390,
    requestAnimationFrame: vi.fn(() => 1),
    cancelAnimationFrame: vi.fn(),
    scrollBy: vi.fn(),
  });
  const root = {
    ownerDocument: document,
    style: {
      setProperty: (k: string, v: string) => values.set(k, v),
      removeProperty: (k: string) => values.delete(k),
    },
    dataset: {} as Record<string, string>,
  };
  const start = () =>
    initializeVisualViewport(root as unknown as HTMLElement, browser as unknown as Window);
  const focus = () => {
    document.activeElement = { matches: () => true };
    document.dispatchEvent(new Event('focusin'));
  };
  return { browser, viewport, document, root, values, start, focus };
}

describe('visual viewport with natural document scrolling', () => {
  it('leaves unsupported browsers untouched', () => {
    const e = environment();
    Object.assign(e.browser, { visualViewport: undefined });
    e.start()();
    expect(e.values.size).toBe(0);
    expect(e.browser.scrollBy).not.toHaveBeenCalled();
  });
  it('raises navigation over an overlay keyboard and follows viewport panning', () => {
    const e = environment();
    const stop = e.start();
    e.focus();
    e.viewport.height = 480;
    e.viewport.dispatchEvent(new Event('resize'));
    expect(e.values.get('--app-keyboard-offset')).toBe('364px');
    expect(e.root.dataset.appKeyboard).toBe('true');
    e.viewport.offsetTop = 50;
    e.viewport.dispatchEvent(new Event('scroll'));
    expect(e.values.get('--app-keyboard-offset')).toBe('314px');
    expect(e.values.get('--app-visual-top')).toBe('50px');
    expect(e.values.get('--app-visual-bottom')).toBe('314px');
    expect(e.browser.scrollBy).not.toHaveBeenCalled();
    stop();
  });
  it('does not double-offset a keyboard that already resizes the layout viewport', () => {
    const e = environment();
    const stop = e.start();
    e.focus();
    e.browser.innerHeight = e.viewport.height = 480;
    e.viewport.dispatchEvent(new Event('resize'));
    expect(e.values.get('--app-keyboard-offset')).toBe('0px');
    expect(e.root.dataset.appKeyboard).toBe('true');
    e.document.activeElement = null;
    e.document.dispatchEvent(new Event('focusout'));
    e.browser.innerHeight = e.viewport.height = 844;
    e.viewport.dispatchEvent(new Event('resize'));
    expect(e.root.dataset.appKeyboard).toBeUndefined();
    stop();
  });
  it('does not misclassify pinch zoom or a window/orientation resize as a keyboard', () => {
    const e = environment();
    const stop = e.start();
    e.focus();
    e.viewport.height = 422;
    e.viewport.scale = 2;
    e.viewport.dispatchEvent(new Event('resize'));
    expect(e.values.get('--app-keyboard-offset')).toBe('0px');
    expect(e.root.dataset.appKeyboard).toBeUndefined();
    e.document.activeElement = null;
    e.viewport.scale = 1;
    e.browser.innerWidth = 844;
    e.browser.innerHeight = e.viewport.height = 390;
    e.browser.dispatchEvent(new Event('resize'));
    expect(e.values.get('--app-visual-height')).toBe('390px');
    expect(e.root.dataset.appKeyboard).toBeUndefined();
    stop();
  });
  it('cleans up all listeners and pending frame work across remounts', () => {
    const e = environment();
    const stop = e.start();
    e.focus();
    stop();
    expect(e.values.size).toBe(0);
    e.viewport.height = 100;
    e.viewport.dispatchEvent(new Event('resize'));
    e.document.dispatchEvent(new Event('focusin'));
    e.browser.dispatchEvent(new Event('resize'));
    expect(e.values.size).toBe(0);
    expect(e.root.dataset.appKeyboard).toBeUndefined();
    expect(e.browser.cancelAnimationFrame).toHaveBeenCalledWith(1);
    e.start()();
    expect(e.values.size).toBe(0);
  });
});
