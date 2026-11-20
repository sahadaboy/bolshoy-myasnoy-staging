import { useEffect, useId, useLayoutEffect, useRef } from 'react';

const ROW_HEIGHT = 44;

/** Native momentum + CSS scroll-snap; scrollend has a debounced fallback for older WebViews. */
export function PickupWheel({
  label,
  values,
  value,
  disabled = [],
  onChoose,
  onMoving,
}: {
  label: string;
  values: string[];
  value: string;
  disabled?: string[];
  onChoose: (value: string) => string;
  onMoving: (moving: boolean) => void;
}) {
  const id = useId();
  const reference = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const expectedTop = useRef(0);
  const current = useRef({ values, value, onChoose, onMoving });
  current.current = { values, value, onChoose, onMoving };
  const optionsKey = values.join(',');

  useLayoutEffect(() => {
    const index = Math.max(0, current.current.values.indexOf(value));
    expectedTop.current = index * ROW_HEIGHT;
    const element = reference.current;
    if (element && Math.abs(element.scrollTop - expectedTop.current) > 0.5)
      element.scrollTo({ top: expectedTop.current, behavior: 'instant' });
  }, [value, optionsKey]);
  useEffect(
    () => () => {
      clearTimeout(timer.current);
      current.current.onMoving(false);
    },
    [],
  );

  const settle = () => {
    clearTimeout(timer.current);
    const element = reference.current;
    if (!element) return;
    const props = current.current;
    const index = Math.max(
      0,
      Math.min(props.values.length - 1, Math.round(element.scrollTop / ROW_HEIGHT)),
    );
    const candidate = props.values[index] || props.value;
    if (candidate === props.value && Math.abs(element.scrollTop - expectedTop.current) < 0.5) {
      props.onMoving(false);
      return;
    }
    const selected = props.onChoose(candidate);
    expectedTop.current = Math.max(0, props.values.indexOf(selected)) * ROW_HEIGHT;
    if (Math.abs(element.scrollTop - expectedTop.current) > 0.5)
      element.scrollTo({ top: expectedTop.current, behavior: 'instant' });
    props.onMoving(false);
  };
  const moveTo = (index: number) => {
    if (index < 0 || !values[index] || disabled.includes(values[index])) return;
    current.current.onMoving(true);
    reference.current?.scrollTo({
      top: index * ROW_HEIGHT,
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
        ? 'instant'
        : 'smooth',
    });
    clearTimeout(timer.current);
    timer.current = setTimeout(settle, 180);
  };

  return (
    <div className="pickup-wheel-column">
      <span className="pickup-wheel-label" id={`${id}-label`}>
        {label}
      </span>
      <div
        className="pickup-wheel"
        ref={reference}
        role="listbox"
        aria-labelledby={`${id}-label`}
        aria-activedescendant={`${id}-${value}`}
        tabIndex={0}
        onScroll={() => {
          clearTimeout(timer.current);
          if (Math.abs((reference.current?.scrollTop || 0) - expectedTop.current) < 0.5) {
            current.current.onMoving(false);
            return;
          }
          current.current.onMoving(true);
          timer.current = setTimeout(settle, 160);
        }}
        onScrollEnd={settle}
        onKeyDown={(event) => {
          if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
          event.preventDefault();
          const enabled = values.filter((item) => !disabled.includes(item));
          const index = enabled.indexOf(value);
          const next =
            event.key === 'Home'
              ? 0
              : event.key === 'End'
                ? enabled.length - 1
                : Math.max(
                    0,
                    Math.min(enabled.length - 1, index + (event.key === 'ArrowDown' ? 1 : -1)),
                  );
          moveTo(values.indexOf(enabled[next]));
        }}
      >
        {values.map((item, index) => (
          <div
            key={item}
            id={`${id}-${item}`}
            role="option"
            aria-selected={item === value}
            aria-disabled={disabled.includes(item)}
            onClick={() => moveTo(index)}
          >
            {item}
          </div>
        ))}
      </div>
    </div>
  );
}
