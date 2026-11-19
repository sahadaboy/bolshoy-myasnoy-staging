import { ArrowRight, RefreshCw, SearchX, WifiOff } from 'lucide-react';
import { Link } from 'react-router-dom';

export function LoadingGrid({ count = 8 }: { count?: number }) {
  return (
    <div className="product-grid" aria-busy="true" aria-label="Загружаем товары">
      {Array.from({ length: count }, (_, index) => (
        <div className="product-card skeleton-card" key={index}>
          <div className="skeleton skeleton-picture" />
          <div className="skeleton skeleton-price" />
          <div className="skeleton skeleton-line" />
          <div className="skeleton skeleton-line short" />
          <div className="skeleton skeleton-button" />
        </div>
      ))}
    </div>
  );
}

export function ErrorState({
  retry,
  compact = false,
  message,
}: {
  retry: () => void;
  compact?: boolean;
  message?: string;
}) {
  return (
    <div className={`state-panel ${compact ? 'compact' : ''}`} role="alert">
      <span className="state-icon">
        <WifiOff size={28} aria-hidden="true" />
      </span>
      <h2>Не удалось загрузить данные</h2>
      <p>{message || 'Проверьте соединение и попробуйте ещё раз.'}</p>
      <button className="button button-outline" onClick={retry}>
        <RefreshCw size={17} aria-hidden="true" /> Попробовать ещё раз
      </button>
    </div>
  );
}

export function EmptyState({ reset }: { reset?: () => void }) {
  return (
    <div className="state-panel">
      <span className="state-icon">
        <SearchX size={30} aria-hidden="true" />
      </span>
      <h2>Пока ничего не нашлось</h2>
      <p>Попробуйте другое название или посмотрите товары в соседней категории.</p>
      {reset ? (
        <button className="button button-primary" onClick={reset}>
          Сбросить фильтры <ArrowRight size={18} aria-hidden="true" />
        </button>
      ) : (
        <Link className="button button-primary" to="/catalog">
          Перейти в каталог <ArrowRight size={18} aria-hidden="true" />
        </Link>
      )}
    </div>
  );
}
