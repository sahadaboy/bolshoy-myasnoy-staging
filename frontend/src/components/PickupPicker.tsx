import { useEffect, useState } from 'react';
import { fetchPickupCalendar, pickupDayLabel, pickupWeekday } from '../lib/pickup';
import { useResource } from '../hooks/useResource';
import { ErrorState } from './States';

export function PickupPicker({
  value,
  onChange,
  refresh,
}: {
  value: string;
  onChange: (value: string) => void;
  refresh: number;
}) {
  const resource = useResource(fetchPickupCalendar);
  const [day, setDay] = useState('');
  useEffect(() => {
    const data = resource.data;
    if (!data) return;
    const selected = data.days.find(
      (item) => item.date === day && item.slots.some((slot) => slot.available),
    );
    if (!selected)
      setDay(data.days.find((item) => item.slots.some((slot) => slot.available))?.date || '');
    if (
      value &&
      !data.days.some((item) => item.slots.some((slot) => slot.at === value && slot.available))
    )
      onChange('');
  }, [resource.data, day, value, onChange]);
  useEffect(() => {
    if (refresh) resource.retry();
  }, [refresh, resource.retry]);
  useEffect(() => {
    const visible = () => {
      if (document.visibilityState === 'visible') resource.retry();
    };
    const timer = setInterval(visible, 60000);
    window.addEventListener('focus', visible);
    document.addEventListener('visibilitychange', visible);
    return () => {
      clearInterval(timer);
      window.removeEventListener('focus', visible);
      document.removeEventListener('visibilitychange', visible);
    };
  }, [resource.retry]);
  const dates = resource.data?.days || [];
  const slots = dates.find((item) => item.date === day)?.slots || [];
  const available = dates.some((item) => item.slots.some((slot) => slot.available));
  return (
    <fieldset className="pickup-picker">
      <legend>Когда хотите забрать заказ?</legend>
      <p>Желаемое время по Москве. Оператор подтвердит возможность получения.</p>
      {resource.data && <p>На сборку нужно не менее {resource.data.preparation_minutes} мин.</p>}
      {resource.error && (
        <ErrorState
          compact
          retry={resource.retry}
          message="Не удалось обновить время самовывоза."
        />
      )}
      {resource.loading && !resource.data ? (
        <p role="status">Проверяем доступное время…</p>
      ) : resource.error && !resource.data ? null : !available ? (
        <p role="status">Сейчас нет доступных интервалов самовывоза. Попробуйте позже.</p>
      ) : (
        <>
          <div className="pickup-days" role="group" aria-label="Дата самовывоза">
            {dates.map((item, index) => (
              <button
                type="button"
                key={item.date}
                disabled={!item.slots.some((slot) => slot.available)}
                aria-pressed={day === item.date}
                aria-label={`${item.weekday}, ${pickupDayLabel(item.date)}`}
                onClick={() => {
                  setDay(item.date);
                  onChange('');
                }}
              >
                <strong>
                  {index === 0 ? 'Сегодня' : index === 1 ? 'Завтра' : pickupWeekday(item.date)}
                </strong>
                <span>{pickupDayLabel(item.date)}</span>
              </button>
            ))}
          </div>
          <div className="pickup-times" role="group" aria-label="Желаемое время самовывоза">
            {slots.map((slot) => (
              <button
                type="button"
                key={slot.at}
                disabled={!slot.available}
                aria-pressed={value === slot.at}
                onClick={() => onChange(slot.at)}
              >
                {slot.time}
              </button>
            ))}
          </div>
          {!value && <p>Выберите время получения.</p>}
        </>
      )}
    </fieldset>
  );
}
