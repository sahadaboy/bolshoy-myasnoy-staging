import { Component, type ReactNode, useEffect, useRef, useState } from 'react';
import { ErrorState, LoadingGrid } from './States';

export function PageSkeleton({
  kind,
}: {
  kind: 'product' | 'cart' | 'profile' | 'orders' | 'ideas';
}) {
  return (
    <div
      className={`loading-surface loading-${kind}`}
      role="status"
      aria-label="Загружаем страницу"
      aria-busy="true"
    >
      {kind === 'product' ? (
        <>
          <div className="skeleton loading-detail-photo" />
          <div className="skeleton skeleton-line" />
          <div className="skeleton skeleton-price" />
          <div className="skeleton loading-control" />
        </>
      ) : kind === 'profile' ? (
        <>
          <div className="loading-person">
            <span className="skeleton" />
            <div className="skeleton skeleton-line" />
          </div>
          <div className="skeleton loading-control" />
          <div className="skeleton loading-control" />
          <div className="skeleton loading-control" />
        </>
      ) : kind === 'ideas' ? (
        <>
          <div className="skeleton loading-idea-photo" />
          <div className="skeleton skeleton-line" />
          <LoadingGrid count={2} />
        </>
      ) : (
        Array.from({ length: 3 }, (_, i) => (
          <div className="loading-row" key={i}>
            {kind === 'cart' && <div className="skeleton loading-row-photo" />}
            <div className="loading-row-copy">
              <div className="skeleton skeleton-line" />
              <div className="skeleton skeleton-line short" />
              <div className="skeleton loading-control" />
            </div>
          </div>
        ))
      )}
    </div>
  );
}

export function RouteSkeleton({ path }: { path: string }) {
  const kind = path.startsWith('/product/')
    ? 'product'
    : path === '/cart'
      ? 'cart'
      : path.startsWith('/profile/orders')
        ? 'orders'
        : path.startsWith('/profile')
          ? 'profile'
          : path.startsWith('/ideas')
            ? 'ideas'
            : null;
  return kind ? <PageSkeleton kind={kind} /> : <LoadingGrid count={4} />;
}

export class PageErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <ErrorState
        message="Не удалось открыть страницу. Повторите загрузку магазина."
        retry={() => window.location.reload()}
      />
    ) : (
      this.props.children
    );
  }
}

export function CartBadge({ count, changeId }: { count: number; changeId: number }) {
  const seen = useRef(changeId);
  const [pulse, setPulse] = useState(0);
  useEffect(() => {
    if (seen.current === changeId) return;
    seen.current = changeId;
    setPulse(count ? changeId : 0);
    const timer = setTimeout(() => setPulse(0), 220);
    return () => clearTimeout(timer);
  }, [changeId]);
  return count > 0 ? (
    <b key={pulse || 'rest'} className={pulse ? 'cart-digit-pulse' : undefined} aria-hidden="true">
      {count}
    </b>
  ) : null;
}
