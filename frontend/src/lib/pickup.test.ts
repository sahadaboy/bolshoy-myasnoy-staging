import { describe, expect, it } from 'vitest';
import {
  availablePickupSlots,
  nearestPickupSlot,
  pickupHours,
  pickupDayLabel,
  pickupLabel,
  pickupWeekday,
  type PickupDay,
} from './pickup';
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

describe('pickup wheel choices from API slots', () => {
  const day: PickupDay = {
    date: '2026-11-21',
    weekday: 'Суббота',
    slots: [
      { at: '2026-11-21T10:00:00+03:00', time: '10:00', available: false },
      { at: '2026-11-21T10:30:00+03:00', time: '10:30', available: true },
      { at: '2026-11-21T13:00:00+03:00', time: '13:00', available: true },
      { at: '2026-11-21T13:30:00+03:00', time: '13:30', available: true },
      { at: '2026-11-21T17:00:00+03:00', time: '17:00', available: true },
    ],
  };
  it('offers only available API hours, preserving gaps and half-hours', () => {
    expect(pickupHours(availablePickupSlots(day))).toEqual(['10', '13', '17']);
    expect(availablePickupSlots(day).map((slot) => slot.time)).not.toContain('10:00');
  });
  it('moves an unavailable minute to a real slot in that hour', () => {
    const slots = availablePickupSlots(day).filter((slot) => slot.time.startsWith('10:'));
    expect(nearestPickupSlot(slots, '10:00')).toBe(day.slots[1]);
    expect(
      nearestPickupSlot(
        availablePickupSlots(day).filter((slot) => slot.time.startsWith('17:')),
        '17:30',
      ),
    ).toBe(day.slots[4]);
  });
  it('keeps a valid time when changing dates and otherwise selects the nearest slot', () => {
    expect(nearestPickupSlot(availablePickupSlots(day), '13:30')).toBe(day.slots[3]);
    expect(nearestPickupSlot(availablePickupSlots(day), '12:00')).toBe(day.slots[2]);
    expect(nearestPickupSlot(availablePickupSlots(day))).toBe(day.slots[1]);
  });
  it('never invents a slot for a closed day', () => {
    expect(availablePickupSlots(undefined)).toEqual([]);
    expect(nearestPickupSlot([], '14:00')).toBeUndefined();
    expect(pickupHours([])).toEqual([]);
  });
});
