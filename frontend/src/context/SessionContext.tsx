import { createContext, useContext, type ReactNode } from 'react';
import { useResource } from '../hooks/useResource';
import { fetchSession } from '../lib/api';
import type { Session } from '../types';

interface SessionState {
  data: Session | null;
  loading: boolean;
  error: string | null;
  retry: () => void;
}
const Context = createContext<SessionState | null>(null);
export function SessionProvider({ children }: { children: ReactNode }) {
  const resource = useResource(fetchSession);
  return <Context.Provider value={resource}>{children}</Context.Provider>;
}
export function useSession() {
  const context = useContext(Context);
  if (!context) throw new Error('useSession requires SessionProvider');
  return context;
}
