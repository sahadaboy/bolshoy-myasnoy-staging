import { useRef, type ReactNode, type RefObject } from 'react';
import { ArrowLeft, ChevronRight, Grid2X2, X } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { categoryImages } from '../data/categoryImages';
import { productImageUrl } from '../lib/api';
import type { Category } from '../types';

export function BackLink({
  fallback = '/catalog',
  children = 'Назад',
}: {
  fallback?: string;
  children?: ReactNode;
}) {
  const navigate = useNavigate();
  return (
    <button
      className="retail-back"
      onClick={() => {
        if (window.history.state?.idx > 0) navigate(-1);
        else navigate(fallback, { replace: true });
      }}
    >
      <ArrowLeft size={19} />
      {children}
    </button>
  );
}

export function SectionHeader({
  title,
  to,
  action,
  actionLabel = 'Все товары',
}: {
  title: string;
  to?: string;
  action?: () => void;
  actionLabel?: string;
}) {
  return (
    <div className="rp-section-heading">
      <h2>{title}</h2>
      {to ? (
        <Link to={to}>
          {actionLabel}
          <ChevronRight size={16} />
        </Link>
      ) : action ? (
        <button onClick={action}>
          {actionLabel}
          <ChevronRight size={16} />
        </button>
      ) : null}
    </div>
  );
}

export function CategoryTile({
  category,
  selected,
  onClick,
}: {
  category: Category;
  selected?: boolean;
  onClick: () => void;
}) {
  const source = productImageUrl(category.image) || categoryImages[category.id];
  return (
    <button onClick={onClick} aria-pressed={selected}>
      <span className="rp-department-photo">
        {source ? (
          <img
            src={source}
            alt=""
            width="80"
            height="72"
            loading="lazy"
            onError={(event) => {
              event.currentTarget.style.display = 'none';
            }}
          />
        ) : (
          <Grid2X2 size={26} strokeWidth={1.4} />
        )}
      </span>
      <span>{category.name}</span>
    </button>
  );
}

export function Sheet({
  reference,
  title,
  children,
}: {
  reference: RefObject<HTMLDialogElement | null>;
  title: string;
  children: ReactNode;
}) {
  const titleId = useRef(`sheet-${Math.random().toString(36).slice(2)}`);
  return (
    <dialog
      ref={reference}
      className="app-dialog retail-sheet"
      aria-labelledby={titleId.current}
      onClick={(event) => {
        if (event.target === event.currentTarget) event.currentTarget.close();
      }}
    >
      <div className="dialog-heading">
        <h2 id={titleId.current}>{title}</h2>
        <button
          className="icon-button"
          autoFocus
          aria-label="Закрыть"
          onClick={() => reference.current?.close()}
        >
          <X size={22} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
