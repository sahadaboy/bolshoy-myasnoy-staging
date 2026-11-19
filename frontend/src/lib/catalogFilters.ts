/** One changed filter starts at page one; category changes discard scoped tags. */
export function catalogFilterParams(params: URLSearchParams, key: string, value: string) {
  const next = new URLSearchParams(params);
  next.delete('page');
  if (value) next.set(key, value);
  else next.delete(key);
  if (key === 'category' || key === 'category_group') {
    next.delete('collection');
    next.delete('tag');
    next.delete(key === 'category' ? 'category_group' : 'category');
  }
  return next;
}
