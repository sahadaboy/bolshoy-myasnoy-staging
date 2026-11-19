import { expect, it } from 'vitest';
import { meatCuts, meatMethods, meatProteins, meatTimes } from '../data/meatGuide';
import {
  chooseMeatAnswer,
  compatiblePriorities,
  compatibleProteins,
  MEAT_CATALOG_URL,
  meatGuideStep,
  meatSafety,
  recommendMeat,
  type MeatAnswers,
} from './meatGuide';

it.each<[MeatAnswers, string]>([
  [{ method: 'kebab', protein: 'pork', priority: 'juicy', time: 'hour' }, 'pork-neck'],
  [
    { method: 'kebab', protein: 'chicken', priority: 'juicy', time: 'hour' },
    'chicken-thigh-fillet',
  ],
  [{ method: 'kebab', protein: 'turkey', priority: 'lean', time: 'hour' }, 'turkey-breast'],
  [{ method: 'fry', protein: 'chicken', priority: 'lean', time: 'quick' }, 'chicken-breast'],
  [{ method: 'fry', protein: 'beef', priority: 'tender', time: 'quick' }, 'beef-tenderloin'],
  [{ method: 'fry', protein: 'beef', priority: 'rich', time: 'quick' }, 'beef-ribeye'],
  [{ method: 'roast', protein: 'chicken', priority: 'juicy', time: 'hour' }, 'chicken-thigh-bone'],
  [{ method: 'stew', protein: 'beef', priority: 'lean', time: 'any' }, 'beef-shoulder'],
  [{ method: 'stew', protein: 'beef', priority: 'rich', time: 'slow' }, 'beef-brisket'],
  [{ method: 'soup', protein: 'chicken', priority: 'rich', time: 'any' }, 'chicken-stock'],
  [{ method: 'soup', protein: 'chicken', priority: 'light', time: 'quick' }, 'chicken-breast'],
  [
    { method: 'mince', protein: 'chicken', priority: 'juicy', time: 'hour' },
    'chicken-thigh-fillet',
  ],
  [{ method: 'mince', protein: 'beef', priority: 'lean', time: 'hour' }, 'beef-shoulder'],
])('matches a reviewed cooking scenario %#', (answers, id) => {
  const result = recommendMeat(answers);
  expect(result.status).toBe('match');
  if (result.status === 'match') expect(result.primary.cut.id).toBe(id);
});

it('honours species, method, preference and time for every offered combination, including alternatives', () => {
  for (const method of meatMethods)
    for (const protein of compatibleProteins(method.id))
      for (const priority of compatiblePriorities(method.id, protein.id))
        for (const time of meatTimes) {
          const answers = { method: method.id, protein: protein.id, priority, time: time.id };
          const result = recommendMeat(answers);
          expect(result).toEqual(recommendMeat(answers));
          expect(['match', 'time-conflict']).toContain(result.status);
          if (result.status !== 'match') continue;
          for (const match of [result.primary, result.alternative].filter(Boolean)) {
            expect(match!.cut.uses[method.id]).toBe(match!.use);
            expect(match!.use.priorities).toContain(priority);
            expect(match!.use.minutes[1]).toBeLessThanOrEqual(time.limit);
            expect(match!.use.minutes[0]).toBeLessThanOrEqual(match!.use.minutes[1]);
            if (protein.id !== 'any') expect(match!.cut.protein).toBe(protein.id);
          }
        }
});

it('never substitutes a quick steak cut for slow beef stew or invents a short cooking time', () => {
  expect(
    recommendMeat({ method: 'stew', protein: 'beef', priority: 'tender', time: 'quick' }),
  ).toEqual({ status: 'time-conflict', requiredMinutes: 180 });
  expect(
    recommendMeat({ method: 'stew', protein: 'beef', priority: 'rich', time: 'hour' }).status,
  ).toBe('time-conflict');
  expect(meatCuts.find((cut) => cut.id === 'beef-tenderloin')!.uses.stew).toBeUndefined();
  expect(meatCuts.find((cut) => cut.id === 'pork-loin')!.uses.stew).toBeUndefined();
});

it('keeps answers when moving back and choosing the same method, but invalidates changed dependencies', () => {
  const answers: MeatAnswers = {
    method: 'fry',
    protein: 'chicken',
    priority: 'quick',
    time: 'quick',
  };
  expect(meatGuideStep('1', answers)).toBe(1);
  expect(chooseMeatAnswer(answers, 'method', 'fry')).toBe(answers);
  const changed = chooseMeatAnswer(answers, 'method', 'stew');
  expect(changed.protein).toBe('chicken');
  expect(changed.time).toBe('quick');
  expect(changed.priority).toBeUndefined();
  expect(meatGuideStep('4', changed)).toBe(2);
  const beefMince: MeatAnswers = {
    method: 'mince',
    protein: 'chicken',
    priority: 'juicy',
    time: 'hour',
  };
  expect(chooseMeatAnswer(beefMince, 'protein', 'beef').priority).toBeUndefined();
  expect(compatiblePriorities('mince', 'beef')).not.toContain('juicy');
});

it('handles incomplete or invalid deep links and answers without falling through to a recommendation', () => {
  expect(meatGuideStep('4', {})).toBe(0);
  expect(meatGuideStep('-1', {})).toBe(0);
  expect(meatGuideStep('garbage', {})).toBe(0);
  expect(recommendMeat({}).status).toBe('incomplete');
  expect(chooseMeatAnswer({}, 'method', 'unknown')).toEqual({});
});

it('has a catalog-independent knowledge base and links to the existing meat group, not a product ID', () => {
  expect(new Set(meatCuts.map((cut) => cut.id)).size).toBe(16);
  expect(new Set(meatCuts.map((cut) => cut.protein)).size).toBe(4);
  expect(MEAT_CATALOG_URL).toBe('/catalog?category_group=meat');
  for (const cut of meatCuts) {
    expect(meatProteins.some((item) => item.id === cut.protein)).toBe(true);
    expect(cut.facts).toHaveLength(2);
    expect(Object.keys(cut.uses).length).toBeGreaterThan(0);
    expect(cut).not.toHaveProperty('price');
    expect(cut).not.toHaveProperty('product_id');
    for (const use of Object.values(cut.uses)) {
      expect(use.description.length).toBeGreaterThan(20);
      expect(use.advice.length).toBeGreaterThan(30);
    }
  }
});

it('distinguishes whole cuts, ground red meat, and all poultry in thermometer advice', () => {
  expect(meatSafety('beef', 'fry')).toContain('63 °C');
  expect(meatSafety('pork', 'roast')).toContain('3 минуты');
  expect(meatSafety('beef', 'mince')).toContain('71 °C');
  expect(meatSafety('chicken', 'mince')).toContain('74 °C');
  expect(meatSafety('turkey', 'roast')).toContain('74 °C');
});
