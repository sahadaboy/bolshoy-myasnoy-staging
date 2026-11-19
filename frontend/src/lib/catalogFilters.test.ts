import { expect, it } from 'vitest';
import { catalogFilterParams } from './catalogFilters';
import { bannerSlides } from '../components/BannerCarousel';
import type { Banner } from '../types';

it('switches tags at page one while keeping the category, search and other filters', () => {
  const original = new URLSearchParams(
    'category=5&tag=milk&page=3&search=20&unit=pcs&available=1&ordering=price',
  );
  const next = catalogFilterParams(original, 'tag', 'sour-cream');
  expect(next.get('category')).toBe('5');
  expect(next.get('tag')).toBe('sour-cream');
  expect(next.has('page')).toBe(false);
  expect(next.get('search')).toBe('20');
  expect(next.get('unit')).toBe('pcs');
  expect(next.get('available')).toBe('1');
  expect(next.get('ordering')).toBe('price');
  expect(original.get('page')).toBe('3');
  const all = catalogFilterParams(next, 'tag', '');
  expect(all.has('tag')).toBe(false);
  expect(all.get('category')).toBe('5');
});

it('clears a previous category tag and collection when opening another category', () => {
  const params = new URLSearchParams(
    'category_group=grocery&tag=rice&page=4&collection=home-fast-dinner',
  );
  const next = catalogFilterParams(params, 'category', '5');
  expect(next.toString()).toBe('category=5');
  expect(catalogFilterParams(next, 'category_group', 'seafood').toString()).toBe(
    'category_group=seafood',
  );
});

it('search resets pagination and retains the selected category tag', () => {
  const next = catalogFilterParams(
    new URLSearchParams('category=5&tag=milk&page=3'),
    'search',
    'Parmalat',
  );
  expect(next.toString()).toBe('category=5&tag=milk&search=Parmalat');
});

it('uses one actual Admin banner image in three slots without changing records', () => {
  const banner: Banner = {
    id: 1,
    image: '/media/current.webp',
    alt_text: 'Текущий баннер',
    target_type: 'catalog',
    target_id: null,
    target_url: '/catalog?all=1',
  };
  const input = [banner];
  const slides = bannerSlides(input);
  expect(slides).toHaveLength(3);
  expect(slides.every((slide) => slide === banner)).toBe(true);
  expect(input).toHaveLength(1);
  const next = { ...banner, id: 2, image: '/media/second.webp' };
  expect(bannerSlides([banner, next]).map((slide) => slide.id)).toEqual([1, 2, 1]);
  expect(bannerSlides([])).toEqual([]);
});
