/** Keep fixed controls inside the visual viewport when a keyboard overlays the page.
 * Telegram stable height still owns the page height; this never locks body scrolling.
 */
export function initializeVisualViewport(root: HTMLElement, browser: Window): () => void {
  const viewport = browser.visualViewport;
  if (!viewport) return () => {};
  const document = root.ownerDocument;
  const properties = [
    '--app-visual-height',
    '--app-visual-top',
    '--app-visual-bottom',
    '--app-keyboard-offset',
  ];
  let restingHeight = viewport.height;
  let width = browser.innerWidth;
  let keyboard = false;
  let frame = 0;
  const editable = () => {
    const element = document.activeElement as HTMLElement | null;
    return element?.matches(
      'textarea:not([readonly]):not([disabled]), input:not([readonly]):not([disabled]):not([type=button]):not([type=submit]):not([type=reset]):not([type=checkbox]):not([type=radio]):not([type=range]):not([type=file]):not([type=color]):not([type=hidden]), [contenteditable="true"]',
    )
      ? element
      : null;
  };
  const sync = () => {
    const height = Number.isFinite(viewport.height)
      ? Math.max(0, viewport.height)
      : browser.innerHeight;
    const top = Number.isFinite(viewport.offsetTop) ? Math.max(0, viewport.offsetTop) : 0;
    const editing = Boolean(editable());
    if ((!editing && !keyboard) || width !== browser.innerWidth) restingHeight = height;
    width = browser.innerWidth;
    // Pinch zoom is not a keyboard. Keep the browser's native zoom/pan behaviour.
    const unzoomed = Math.abs(viewport.scale - 1) < 0.01;
    const offset =
      unzoomed && (editing || keyboard) ? Math.max(0, browser.innerHeight - height - top) : 0;
    keyboard = unzoomed && (editing || keyboard) && (offset > 1 || height < restingHeight - 1);
    if (!keyboard && !editing) restingHeight = height;
    root.style.setProperty('--app-visual-height', `${height}px`);
    root.style.setProperty('--app-visual-top', `${top}px`);
    root.style.setProperty(
      '--app-visual-bottom',
      `${Math.max(0, browser.innerHeight - height - top)}px`,
    );
    root.style.setProperty('--app-keyboard-offset', `${keyboard ? offset : 0}px`);
    if (keyboard) root.dataset.appKeyboard = 'true';
    else delete root.dataset.appKeyboard;
  };
  const reveal = () => {
    browser.cancelAnimationFrame(frame);
    frame = browser.requestAnimationFrame(() => {
      sync();
      const element = editable();
      if (!element || !keyboard) return;
      const rect = element.getBoundingClientRect();
      const dialog = element.closest<HTMLDialogElement>('dialog[open]');
      const shell = document.querySelector<HTMLElement>('.rp');
      const safeTop = shell ? parseFloat(browser.getComputedStyle(shell).paddingTop) || 0 : 0;
      const nav = document.querySelector<HTMLElement>('.rp-nav');
      const top = dialog
        ? dialog.getBoundingClientRect().top + 12
        : viewport.offsetTop + safeTop + 12;
      const bottom =
        (dialog
          ? dialog.getBoundingClientRect().bottom
          : Math.min(
              viewport.offsetTop + viewport.height,
              nav?.getBoundingClientRect().top ?? Infinity,
            )) - 12;
      const delta =
        rect.top < top
          ? rect.top - top
          : rect.bottom > bottom
            ? Math.min(rect.bottom - bottom, rect.top - top)
            : 0;
      if (delta && bottom > top) {
        if (dialog) dialog.scrollBy({ top: delta, behavior: 'instant' });
        else browser.scrollBy({ top: delta, behavior: 'instant' });
      }
    });
  };
  const resize = () => {
    sync();
    reveal();
  };
  sync();
  viewport.addEventListener('resize', resize);
  viewport.addEventListener('scroll', sync);
  browser.addEventListener('resize', resize);
  document.addEventListener('focusin', resize);
  document.addEventListener('focusout', resize);
  return () => {
    browser.cancelAnimationFrame(frame);
    viewport.removeEventListener('resize', resize);
    viewport.removeEventListener('scroll', sync);
    browser.removeEventListener('resize', resize);
    document.removeEventListener('focusin', resize);
    document.removeEventListener('focusout', resize);
    properties.forEach((property) => root.style.removeProperty(property));
    delete root.dataset.appKeyboard;
  };
}
