import { useLayoutEffect } from 'react';
import { useLocation, useNavigationType } from 'react-router-dom';
import { navigationMemory } from '../lib/navigationMemory';

export function initializeScrollMemory(
  location: { pathname: string; search: string; key: string },
  action: string,
  memory = navigationMemory
) {
  const previous = window.history.scrollRestoration;
  window.history.scrollRestoration = 'manual';
  const target = memory.enter(location, action);
  let y = target;
  let restoring = true;
  let frame = 0;
  let observer: ResizeObserver | undefined;
  const stop = () => {
    restoring = false;
    cancelAnimationFrame(frame);
    observer?.disconnect();
    y = window.scrollY;
  };
  const restore = () => {
    if (!restoring) return;
    window.scrollTo({ top: target, behavior: 'instant' });
    if (Math.abs(window.scrollY - target) < 1) stop();
  };
  // Cached content is already in the DOM: restore before paint, without a jump.
  restore();
  const main = document.getElementById('main');
  if (restoring && main && typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(restore);
    });
    observer.observe(main);
  }
  const track = () => {
    if (!restoring) {
      y = window.scrollY;
      memory.save(location, y);
    }
  };
  const key = (event: KeyboardEvent) => {
    if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(event.key))
      stop();
  };
  window.addEventListener('scroll', track, { passive: true });
  window.addEventListener('wheel', stop, { passive: true });
  window.addEventListener('pointerdown', stop, { passive: true });
  window.addEventListener('keydown', key);
  return () => {
    cancelAnimationFrame(frame);
    observer?.disconnect();
    memory.save(location, y);
    window.removeEventListener('scroll', track);
    window.removeEventListener('wheel', stop);
    window.removeEventListener('pointerdown', stop);
    window.removeEventListener('keydown', key);
    window.history.scrollRestoration = previous;
  };
}

export function ScrollMemory() {
  const location = useLocation();
  const action = useNavigationType();
  useLayoutEffect(() => initializeScrollMemory(location, action), [location.key, action]);
  return null;
}
