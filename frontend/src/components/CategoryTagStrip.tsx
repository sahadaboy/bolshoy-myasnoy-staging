import { useEffect, useRef, useState } from 'react';
import type { CatalogTag } from '../types';

export function CategoryTagStrip({
  tags,
  selected,
  onSelect,
}: {
  tags: CatalogTag[];
  selected: string;
  onSelect: (slug: string) => void;
}) {
  const track = useRef<HTMLDivElement>(null);
  const [more, setMore] = useState(false);
  useEffect(() => {
    const element = track.current;
    if (!element) return;
    const active = element.querySelector<HTMLElement>('[aria-pressed="true"]');
    if (active) {
      const left =
        active.getBoundingClientRect().left -
        element.getBoundingClientRect().left +
        element.scrollLeft;
      if (left < element.scrollLeft) element.scrollLeft = left;
      else if (left + active.offsetWidth > element.scrollLeft + element.clientWidth)
        element.scrollLeft = left + active.offsetWidth - element.clientWidth;
    }
    const update = () =>
      setMore(element.scrollWidth - element.clientWidth - element.scrollLeft > 1);
    update();
    element.addEventListener('scroll', update, { passive: true });
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => {
      element.removeEventListener('scroll', update);
      observer.disconnect();
    };
  }, [tags, selected]);
  if (!tags.length) return null;
  return (
    <div className="category-tag-strip" data-more={more ? 'true' : 'false'}>
      <div className="category-tag-track" ref={track} role="group" aria-label="Уточнить категорию">
        <button type="button" aria-pressed={!selected} onClick={() => onSelect('')}>
          Все
        </button>
        {tags.map((tag) => (
          <button
            type="button"
            key={tag.slug}
            aria-pressed={selected === tag.slug}
            onClick={() => onSelect(tag.slug)}
          >
            {tag.label}
          </button>
        ))}
      </div>
    </div>
  );
}
