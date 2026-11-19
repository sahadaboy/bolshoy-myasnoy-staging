export const STORE_TIME_ZONE = 'Europe/Moscow';

const clock = new Intl.DateTimeFormat('en-GB', {
  timeZone: STORE_TIME_ZONE,
  weekday: 'short',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
});
const weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const russianDays = [
  ['понедельник', 'пн'],
  ['вторник', 'вт'],
  ['среда', 'ср'],
  ['четверг', 'чт'],
  ['пятница', 'пт'],
  ['суббота', 'сб'],
  ['воскресенье', 'вс'],
];

/** ISO weekday and delay to the next store midnight, independent of device timezone. */
export function storeClock(now = new Date()) {
  const parts = Object.fromEntries(
    clock.formatToParts(now).map(({ type, value }) => [type, value]),
  );
  const seconds = Number(parts.hour) * 3600 + Number(parts.minute) * 60 + Number(parts.second);
  return {
    weekday: weekdays.indexOf(parts.weekday) + 1,
    untilMidnight: (86400 - seconds) * 1000 - now.getUTCMilliseconds(),
  };
}

function dayNumber(value: string): number {
  return (
    russianDays.findIndex((names) =>
      names.includes(value.trim().toLocaleLowerCase('ru-RU').replace(/\./g, '')),
    ) + 1
  );
}

function rowDays(label: string): number[] {
  if (/^ежедневно$/i.test(label)) return [1, 2, 3, 4, 5, 6, 7];
  return [
    ...new Set(
      label.split(/[,;/]/).flatMap((part) => {
        const range = part.trim().split(/\s*[–—-]\s*/);
        const start = dayNumber(range[0]);
        if (!start) return [];
        if (range.length === 1) return [start];
        const end = range.length === 2 ? dayNumber(range[1]) : 0;
        if (!end) return [];
        const days = [start];
        while (days[days.length - 1] !== end) days.push((days[days.length - 1] % 7) + 1);
        return days;
      }),
    ),
  ];
}

/** Preserve Admin text and hours; unknown labels are never guessed by row position. */
export function parseOpeningHours(value: string) {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const match =
        line.match(/^([^\d:]+?)(?::\s*|\s+[—–-]\s*)(.+)$/) ||
        line.match(/^(.+?)\s+(\d{1,2}[:.]\d{2}.*)$/);
      const label = (match?.[1] || line).trim();
      return { label, hours: match?.[2].trim() || '', days: rowDays(label) };
    });
}
