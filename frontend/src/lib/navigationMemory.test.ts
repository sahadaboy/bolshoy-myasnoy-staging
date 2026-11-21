import { describe, expect, it } from 'vitest';
import { NavigationMemory } from './navigationMemory';

const catalog = { pathname: '/catalog', search: '?category=2&tag=steak&ordering=price', key: 'c1' };
const ideas = { pathname: '/ideas', search: '?meal=dinner', key: 'i1' };

describe('main tab memory', () => {
  it('restores catalog/ideas filters and independent scroll positions on PUSH tab switches', () => {
    const memory = new NavigationMemory();
    memory.enter(catalog, 'PUSH');
    memory.save(catalog, 1460);
    memory.enter(ideas, 'PUSH');
    memory.save(ideas, 420);
    expect(memory.destination('/catalog', ideas)).toBe('/catalog' + catalog.search);
    expect(memory.enter({ ...catalog, key: 'c2' }, 'PUSH')).toBe(1460);
    expect(memory.destination('/ideas', catalog)).toBe('/ideas?meal=dinner');
    expect(memory.enter({ ...ideas, key: 'i2' }, 'PUSH')).toBe(420);
  });

  it('keeps the selected tab URL and resets scroll for an explicitly changed filter', () => {
    const memory = new NavigationMemory();
    memory.save(catalog, 1460);
    expect(memory.destination('/catalog', catalog)).toBe('/catalog' + catalog.search);
    expect(memory.enter({ ...catalog, search: '?category=3', key: 'c2' }, 'PUSH')).toBe(0);
  });

  it('keeps separate history positions for Back/Forward and ignores child routes as tab state', () => {
    const memory = new NavigationMemory();
    memory.save(catalog, 700);
    memory.save({ ...catalog, key: 'c2' }, 900);
    memory.save({ pathname: '/product/5', search: '', key: 'p' }, 50);
    expect(memory.enter(catalog, 'POP')).toBe(700);
    expect(memory.enter({ ...catalog, key: 'c2' }, 'POP')).toBe(900);
    expect(memory.destination('/catalog', ideas)).toBe('/catalog' + catalog.search);
  });

  it('limits history memory and gives new tabs an initial position of zero', () => {
    const memory = new NavigationMemory();
    expect(memory.enter({ pathname: '/cart', search: '', key: 'cart' }, 'PUSH')).toBe(0);
    for (let i = 0; i < 65; i++) memory.save({ ...catalog, key: String(i) }, i + 1);
    expect(memory.enter({ ...catalog, key: '0' }, 'POP')).toBe(0);
    expect(memory.enter({ ...catalog, key: '64' }, 'POP')).toBe(65);
  });

  it('does not restore an old Liquid Glass preference from a saved tab URL', () => {
    const memory = new NavigationMemory();
    memory.save({ ...catalog, search: '?all=1&nav=glass' }, 700);
    expect(memory.destination('/catalog', ideas)).toBe('/catalog?all=1');
    expect(memory.enter({ ...catalog, search: '?all=1&nav=classic', key: 'c2' }, 'PUSH')).toBe(700);
  });
});
