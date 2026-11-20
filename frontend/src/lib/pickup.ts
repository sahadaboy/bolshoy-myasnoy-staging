import { get } from './api';
export interface PickupCalendar {
  timezone: string;
  generated_at: string;
  preparation_minutes: number;
  configured: boolean;
  days: {
    date: string;
    weekday: string;
    slots: { at: string; time: string; available: boolean }[];
  }[];
}
export const fetchPickupCalendar = (signal: AbortSignal) =>
  get<PickupCalendar>('/api/pickup-slots/', signal);
export type PickupDay = PickupCalendar['days'][number];
export type PickupSlot = PickupDay['slots'][number];

export function availablePickupSlots(day: PickupDay | undefined): PickupSlot[] {
  return (day?.slots || []).filter((slot) => slot.available);
}

/** Select an actual API slot, never synthesize a datetime or fill gaps in opening hours. */
export function nearestPickupSlot(slots: PickupSlot[], time = ''): PickupSlot | undefined {
  const minutes = (value: string) => Number(value.slice(0, 2)) * 60 + Number(value.slice(3, 5));
  const target = minutes(time);
  return slots.reduce<PickupSlot | undefined>((best, slot) => {
    if (!best) return slot;
    if (!time) return minutes(slot.time) < minutes(best.time) ? slot : best;
    const distance = Math.abs(minutes(slot.time) - target);
    const previous = Math.abs(minutes(best.time) - target);
    // On a tie prefer the later slot, rather than silently moving pickup earlier.
    return distance < previous || (distance === previous && slot.time > best.time) ? slot : best;
  }, undefined);
}

export function pickupHours(slots: PickupSlot[]): string[] {
  return [...new Set(slots.map((slot) => slot.time.slice(0, 2)))].sort();
}
export function pickupLabel(value: string | null | undefined) {
  return value
    ? new Intl.DateTimeFormat('ru-RU', {
        timeZone: 'Europe/Moscow',
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      }).format(new Date(value))
    : 'Время не указано';
}
export function pickupDayLabel(value: string) {
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone: 'Europe/Moscow',
    day: 'numeric',
    month: 'short',
  }).format(new Date(value + 'T12:00:00+03:00'));
}
export function pickupWeekday(value: string) {
  return new Intl.DateTimeFormat('ru-RU', { timeZone: 'Europe/Moscow', weekday: 'short' }).format(
    new Date(value + 'T12:00:00+03:00'),
  );
}
