type Location = { pathname: string; search: string; key: string };
const tabs = new Set(['/catalog', '/ideas', '/cart', '/profile']);
function tabSearch(search: string): string {
  const params = new URLSearchParams(search);
  // The glass comparison switch is an app preference, not a saved tab filter.
  params.delete('nav');
  return params.size ? `?${params}` : '';
}

/** Four tab URLs/positions plus bounded browser history, never mounted page trees. */
export class NavigationMemory {
  private history = new Map<string, number>();
  private tabs = new Map<string, { search: string; y: number }>();
  destination(to: string, current: Pick<Location, 'pathname' | 'search'>): string {
    return to + (current.pathname === to ? current.search : this.tabs.get(to)?.search || '');
  }
  enter(location: Location, action: string): number {
    const tab = this.tabs.get(location.pathname);
    const search = tabSearch(location.search);
    const y =
      action === 'POP' ? this.history.get(location.key) || 0 : tab?.search === search ? tab.y : 0;
    if (tabs.has(location.pathname)) this.tabs.set(location.pathname, { search, y });
    return y;
  }
  save(location: Location, y: number) {
    y = Math.max(0, y);
    this.history.delete(location.key);
    this.history.set(location.key, y);
    if (tabs.has(location.pathname))
      this.tabs.set(location.pathname, { search: tabSearch(location.search), y });
    while (this.history.size > 64) this.history.delete(this.history.keys().next().value!);
  }
}

export const navigationMemory = new NavigationMemory();
