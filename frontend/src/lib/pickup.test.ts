import { describe, expect, it } from 'vitest';
import { pickupDayLabel, pickupLabel, pickupWeekday } from './pickup';
describe('store-local pickup labels', () => {
  it('uses Moscow time for equivalent instants from any device timezone', () => {
    expect(pickupLabel('2026-11-22T11:30:00Z')).toContain('14:30');
    expect(pickupLabel('2026-11-22T11:30:00Z')).toBe(pickupLabel('2026-11-22T14:30:00+03:00'));
  });
  it('keeps the selected store date across UTC midnight', () => {
    expect(pickupLabel('2026-11-20T22:30:00Z')).toContain('21.11.2026');
    expect(pickupDayLabel('2026-11-21')).toContain('21');
    expect(pickupWeekday('2026-11-23')).toBe('пн');
  });
  it('does not invent pickup dates for old orders', () => {
    expect(pickupLabel(null)).toBe('Время не указано');
    expect(pickupLabel(undefined)).toBe('Время не указано');
  });
});
