import { expect, it } from 'vitest';
import { parseOpeningHours, storeClock } from './storeHours';

it('changes the store day at Moscow midnight, including the Sunday/Monday boundary', () => {
  expect(storeClock(new Date('2026-11-22T20:59:59.900Z'))).toEqual({
    weekday: 7,
    untilMidnight: 100,
  });
  expect(storeClock(new Date('2026-11-22T21:00:00.000Z'))).toEqual({
    weekday: 1,
    untilMidnight: 86400000,
  });
  expect(storeClock(new Date('2026-11-18T21:00:00Z')).weekday).toBe(4);
});

it('uses the same instant regardless of the device timezone or represented offset', () => {
  expect(storeClock(new Date('2026-11-19T14:00:00-07:00')).weekday).toBe(5);
  expect(storeClock(new Date('2026-11-20T06:00:00+09:00')).weekday).toBe(5);
});

it('keeps real Admin hours and identifies days by name after a reorder', () => {
  const rows = parseOpeningHours(
    'Среда: 08:00–19:00\r\nПонедельник: 08:00–20:00\n\nВоскресенье — выходной',
  );
  expect(rows).toEqual([
    { label: 'Среда', hours: '08:00–19:00', days: [3] },
    { label: 'Понедельник', hours: '08:00–20:00', days: [1] },
    { label: 'Воскресенье', hours: 'выходной', days: [7] },
  ]);
});

it('supports grouped days and abbreviations without inventing unknown schedule rows', () => {
  expect(parseOpeningHours('Пн.–Сб.: 08:00–20:00')[0].days).toEqual([1, 2, 3, 4, 5, 6]);
  expect(parseOpeningHours('Вс–Вт: 09:00–18:00')[0].days).toEqual([7, 1, 2]);
  expect(parseOpeningHours('Пн, Ср: 09:00–18:00')[0].days).toEqual([1, 3]);
  expect(parseOpeningHours('Ежедневно: 08:00–20:00')[0].days).toHaveLength(7);
  expect(parseOpeningHours('По договорённости')[0]).toEqual({
    label: 'По договорённости',
    hours: '',
    days: [],
  });
  expect(parseOpeningHours('')).toEqual([]);
  expect(parseOpeningHours('Пн 08:00–20:00')[0]).toEqual({
    label: 'Пн',
    hours: '08:00–20:00',
    days: [1],
  });
});
