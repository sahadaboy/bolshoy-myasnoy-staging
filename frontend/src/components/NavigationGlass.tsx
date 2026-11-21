import { Component, lazy, Suspense, useEffect, useState, type ReactNode } from 'react';

type Design = 'classic' | 'glass' | 'glass-lite';
type Renderer = 'native' | 'drawn' | null;
const storageKey = 'bm:navigation:v1';
const designValue = (value: string | null): Design | null =>
  value === 'classic' || value === 'glass' || value === 'glass-lite' ? value : null;

// Import only the decorative layer: navigation stays usable while it loads or fails.
const Glass = lazy(() => import('glisse').then((module) => ({ default: module.Glass })));
const fallback = <div className="retail-nav-surface" aria-hidden="true" />;

function detectRenderer(): Renderer {
  if (
    typeof ResizeObserver === 'undefined' ||
    typeof CSS === 'undefined' ||
    !(
      CSS.supports('backdrop-filter', 'blur(1px)') ||
      CSS.supports('-webkit-backdrop-filter', 'blur(1px)')
    )
  )
    return null;
  try {
    if (!document.createElement('canvas').getContext('2d')) return null;
    // Matches Glisse 0.6.0's live SVG backdrop support; no catalog-wide filter.
    if (/Chrom(?:e|ium)\//.test(navigator.userAgent)) return 'native';
    // Glisse draws marked content in WebKit, which needs WebGL2.
    if (!/AppleWebKit\//.test(navigator.userAgent)) return null;
    const context = document.createElement('canvas').getContext('webgl2', {
      failIfMajorPerformanceCaveat: true,
    });
    if (!context) return null;
    context.getExtension('WEBGL_lose_context')?.loseContext();
    return 'drawn';
  } catch {
    return null;
  }
}

export function useNavigationAppearance(search: string) {
  const [saved, setSaved] = useState<Design>(() => {
    try {
      return designValue(localStorage.getItem(storageKey)) ?? 'glass';
    } catch {
      return 'glass';
    }
  });
  const design = designValue(new URLSearchParams(search).get('nav')) ?? saved;
  const [renderer, setRenderer] = useState<Renderer>(null);
  useEffect(() => {
    setSaved(design);
    try {
      localStorage.setItem(storageKey, design);
    } catch {
      // Private/restricted storage still supports the URL switch for this session.
    }
  }, [design]);

  useEffect(() => {
    if (design !== 'glass') {
      setRenderer(null);
      return;
    }
    const motion = matchMedia('(prefers-reduced-motion: reduce)');
    const transparency = matchMedia('(prefers-reduced-transparency: reduce)');
    const device = navigator as Navigator & {
      deviceMemory?: number;
      connection?: EventTarget & { saveData?: boolean };
    };
    let available: Renderer | undefined;
    const update = () => {
      const light =
        motion.matches ||
        transparency.matches ||
        device.connection?.saveData ||
        (device.hardwareConcurrency > 0 && device.hardwareConcurrency <= 2) ||
        (device.deviceMemory !== undefined && device.deviceMemory <= 2) ||
        document.hidden ||
        document.documentElement.dataset.appKeyboard === 'true';
      if (!light && available === undefined) available = detectRenderer();
      setRenderer(light ? null : (available ?? null));
    };
    update();
    motion.addEventListener('change', update);
    transparency.addEventListener('change', update);
    device.connection?.addEventListener('change', update);
    document.addEventListener('visibilitychange', update);
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-app-keyboard'],
    });
    return () => {
      motion.removeEventListener('change', update);
      transparency.removeEventListener('change', update);
      device.connection?.removeEventListener('change', update);
      document.removeEventListener('visibilitychange', update);
      observer.disconnect();
    };
  }, [design]);

  return { design: design === 'classic' ? 'classic' : 'glass', renderer };
}

class GlassBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? fallback : this.props.children;
  }
}

export function NavigationGlass({ enabled }: { enabled: boolean }) {
  if (!enabled) return fallback;
  return (
    <GlassBoundary>
      <Suspense fallback={fallback}>
        <Glass className="retail-nav-surface" aria-hidden="true" />
      </Suspense>
    </GlassBoundary>
  );
}
