import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { restoreCustomerSession, CustomerAuthError } from '../lib/customerSession';
import type { Session } from '../types';

interface SessionState {
  authenticationRequired: boolean;
  data: Session | null;
  loading: boolean;
  error: string | null;
  retry: () => void;
}
const Context = createContext<SessionState | null>(null);
export function SessionProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [authenticationRequired, setAuthenticationRequired] = useState(false);
  const generation = useRef(0);
  const retry = useCallback(() => {
    const current = ++generation.current;
    setLoading(true);
    setError(null);
    void restoreCustomerSession()
      .then((value) => {
        if (current === generation.current) {
          setData(value);
          setAuthenticationRequired(false);
        }
      })
      .catch((reason) => {
        if (current !== generation.current) return;
        if (reason instanceof CustomerAuthError && reason.status === 401) {
          setData(null);
          setAuthenticationRequired(true);
        }
        setError(
          reason instanceof CustomerAuthError
            ? reason.message
            : 'Не удалось проверить сессию. Проверьте соединение и повторите попытку.',
        );
      })
      .finally(() => {
        if (current === generation.current) setLoading(false);
      });
  }, []);
  useEffect(() => {
    const visible = () => {
      if (document.visibilityState === 'visible') retry();
    };
    const expired = () => {
      setData(null);
      setAuthenticationRequired(true);
      setError('Сессия завершилась. Откройте магазин заново из меню Telegram-бота.');
      retry();
    };
    retry();
    const timer = setInterval(visible, 30000);
    window.addEventListener('focus', visible);
    window.addEventListener('pageshow', visible);
    window.addEventListener('online', visible);
    document.addEventListener('visibilitychange', visible);
    window.addEventListener('miniapp:session-expired', expired);
    return () => {
      generation.current++;
      clearInterval(timer);
      window.removeEventListener('focus', visible);
      window.removeEventListener('online', visible);
      window.removeEventListener('pageshow', visible);
      document.removeEventListener('visibilitychange', visible);
      window.removeEventListener('miniapp:session-expired', expired);
    };
  }, [retry]);
  return (
    <Context.Provider value={{ data, loading, error, retry, authenticationRequired }}>
      {children}
    </Context.Provider>
  );
}
export function useSession() {
  const context = useContext(Context);
  if (!context) throw new Error('useSession requires SessionProvider');
  return context;
}
