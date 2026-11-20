import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { CalendarDays, ChevronRight, X } from 'lucide-react';
import {
  availablePickupSlots,
  fetchPickupCalendar,
  nearestPickupSlot,
  pickupDayLabel,
  pickupHours,
  pickupLabel,
  pickupWeekday,
} from '../lib/pickup';
import { useResource } from '../hooks/useResource';
import { ErrorState } from './States';
import { PickupWheel } from './PickupWheel';

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
  const reference = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState({ date: '', at: '' });
  const [moving, setMoving] = useState({ hour: false, minute: false });
  const dates = resource.data?.days || [];
  const day =
    dates.find((item) => item.date === draft.date && availablePickupSlots(item).length) ||
    dates.find((item) => availablePickupSlots(item).length);
  const slots = availablePickupSlots(day);
  const slot =
    slots.find((item) => item.at === draft.at) || nearestPickupSlot(slots, draft.at.slice(11, 16));
  const hours = pickupHours(slots);
  const hour = slot?.time.slice(0, 2) || '';
  const minute = slot?.time.slice(3, 5) || '';

  useEffect(() => {
    if (
      value &&
      resource.data &&
      !resource.data.days.some((item) =>
        item.slots.some((slot) => slot.at === value && slot.available),
      )
    )
      onChange('');
  }, [resource.data, value, onChange]);
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
  useLayoutEffect(() => {
    if (!open) return;
    const previous = document.documentElement.style.overflow;
    document.documentElement.style.overflow = 'hidden';
    reference.current?.showModal();
    reference.current
      ?.querySelector('[aria-pressed="true"]')
      ?.scrollIntoView({ inline: 'center', block: 'nearest' });
    return () => {
      document.documentElement.style.overflow = previous;
    };
  }, [open]);

  const updateMoving = (column: 'hour' | 'minute', value: boolean) =>
    setMoving((previous) =>
      previous[column] === value ? previous : { ...previous, [column]: value },
    );
  const choose = (time: string, column: 'hour' | 'minute') => {
    const selected = nearestPickupSlot(
      slots.filter((item) => item.time.startsWith(time.slice(0, 2) + ':')),
      time,
    );
    if (selected)
      setDraft((previous) =>
        previous.date === day!.date && previous.at === selected.at
          ? previous
          : { date: day!.date, at: selected.at },
      );
    return selected?.time.slice(column === 'hour' ? 0 : 3, column === 'hour' ? 2 : 5) || '';
  };
  const show = () => {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    const selectedDay =
      dates.find((item) => item.slots.some((slot) => slot.available && slot.at === value)) ||
      dates.find((item) => availablePickupSlots(item).length);
    const selected =
      selectedDay?.slots.find((item) => item.at === value && item.available) ||
      nearestPickupSlot(availablePickupSlots(selectedDay));
    setDraft({ date: selectedDay?.date || '', at: selected?.at || '' });
    setMoving({ hour: false, minute: false });
    setOpen(true);
    resource.retry();
  };

  return (
    <div className="pickup-picker">
      <button
        type="button"
        className="pickup-field"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={show}
      >
        <CalendarDays size={21} aria-hidden="true" />
        <span>
          <strong>Когда хотите забрать заказ?</strong>
          <span>
            {value
              ? pickupLabel(value)
              : resource.loading && !resource.data
                ? 'Проверяем доступное время…'
                : 'Выберите дату и время'}
          </span>
        </span>
        <ChevronRight size={19} aria-hidden="true" />
      </button>
      <dialog
        ref={reference}
        className="app-dialog pickup-sheet"
        aria-labelledby={titleId}
        onClose={() => setOpen(false)}
        onClick={(event) => {
          if (event.target === event.currentTarget) reference.current?.close();
        }}
      >
        {open && (
          <>
            <header className="pickup-sheet-heading">
              <h2 id={titleId}>Когда заберёте заказ?</h2>
              <button
                type="button"
                className="icon-button"
                autoFocus
                aria-label="Закрыть выбор времени"
                onClick={() => reference.current?.close()}
              >
                <X size={22} />
              </button>
            </header>
            <div className="pickup-sheet-body">
              <div className="pickup-days" role="group" aria-label="Дата самовывоза">
                {dates.map((item, index) => (
                  <button
                    type="button"
                    key={item.date}
                    disabled={!availablePickupSlots(item).length}
                    aria-pressed={day?.date === item.date}
                    aria-label={`${item.weekday}, ${pickupDayLabel(item.date)}`}
                    onClick={() => {
                      const selected = nearestPickupSlot(availablePickupSlots(item), slot?.time);
                      setDraft({ date: item.date, at: selected?.at || '' });
                      setMoving({ hour: false, minute: false });
                    }}
                  >
                    <strong>
                      {index === 0 ? 'Сегодня' : index === 1 ? 'Завтра' : pickupWeekday(item.date)}
                    </strong>
                    <span>{pickupDayLabel(item.date)}</span>
                  </button>
                ))}
              </div>
              {resource.error && (
                <ErrorState
                  compact
                  retry={resource.retry}
                  message="Не удалось обновить время самовывоза."
                />
              )}
              {!resource.data && resource.loading ? (
                <p role="status">Проверяем доступное время…</p>
              ) : !slot ? (
                !resource.error && (
                  <p role="status">Сейчас нет доступных интервалов самовывоза. Попробуйте позже.</p>
                )
              ) : (
                <div className="pickup-wheels" role="group" aria-label="Желаемое время самовывоза">
                  <div className="pickup-wheel-highlight" aria-hidden="true" />
                  <PickupWheel
                    key={day?.date + '-hour'}
                    label="Часы"
                    values={hours}
                    value={hour}
                    onChoose={(value) => choose(`${value}:${minute}`, 'hour')}
                    onMoving={(value) => updateMoving('hour', value)}
                  />
                  <span className="pickup-wheel-colon" aria-hidden="true">
                    :
                  </span>
                  <PickupWheel
                    key={day?.date + '-minute'}
                    label="Минуты"
                    values={['00', '30']}
                    value={minute}
                    disabled={['00', '30'].filter(
                      (value) => !slots.some((item) => item.time === `${hour}:${value}`),
                    )}
                    onChoose={(value) => choose(`${hour}:${value}`, 'minute')}
                    onMoving={(value) => updateMoving('minute', value)}
                  />
                </div>
              )}
              <p className="pickup-sheet-note">
                Время по Москве.{' '}
                {resource.data && `На сборку — от ${resource.data.preparation_minutes} мин. `}
                Возможность получения подтвердит оператор.
              </p>
            </div>
            <footer className="pickup-sheet-footer">
              <button
                type="button"
                className="button button-primary"
                disabled={
                  !slot || resource.loading || !!resource.error || moving.hour || moving.minute
                }
                onClick={() => {
                  if (slot) {
                    onChange(slot.at);
                    reference.current?.close();
                  }
                }}
              >
                Выбрать время
              </button>
            </footer>
          </>
        )}
      </dialog>
    </div>
  );
}
