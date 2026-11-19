import { useEffect, useState } from 'react';
import { storeClock } from '../lib/storeHours';

export function useStoreWeekday() {
  const [today, setToday] = useState(() => storeClock().weekday);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const refresh = () => {
      clearTimeout(timer);
      const time = storeClock();
      setToday(time.weekday);
      timer = setTimeout(refresh, time.untilMidnight + 50);
    };
    const visible = () => {
      if (document.visibilityState === 'visible') refresh();
    };
    refresh();
    document.addEventListener('visibilitychange', visible);
    window.addEventListener('pageshow', refresh);
    window.addEventListener('focus', refresh);
    return () => {
      clearTimeout(timer);
      document.removeEventListener('visibilitychange', visible);
      window.removeEventListener('pageshow', refresh);
      window.removeEventListener('focus', refresh);
    };
  }, []);
  return today;
}
