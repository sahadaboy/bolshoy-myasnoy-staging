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
