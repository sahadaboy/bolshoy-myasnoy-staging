import { type FormEvent, Suspense, useEffect, useState } from 'react';
import {
  BookOpen,
  ChevronRight,
  Grid2X2,
  Search,
  ShoppingBasket,
  SlidersHorizontal,
  UserRound,
  X,
} from 'lucide-react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useCart } from '../context/CartContext';
import '../preview/preview.css';
import '../retail.css';
import { STORE_BRAND } from '../data/brand';

const navigation = [
  { to: '/catalog', label: 'Каталог', icon: Grid2X2 },
  { to: '/ideas', label: 'Идеи', icon: BookOpen },
  { to: '/cart', label: 'Корзина', icon: ShoppingBasket },
  { to: '/profile', label: 'Профиль', icon: UserRound },
];

export function SearchForm({ onFilters }: { onFilters?: () => void }) {
  const navigate = useNavigate();
  const { search } = useLocation();
  const query = new URLSearchParams(search).get('search') || '';
  const [value, setValue] = useState(query);
  useEffect(() => {
    setValue(query);
  }, [query]);
  useEffect(() => {
    if (value.trim() === query) return;
    const timeout = window.setTimeout(() => {
      const params = new URLSearchParams(search);
      if (value.trim()) params.set('search', value.trim());
      else params.delete('search');
      navigate(`/catalog${params.size ? `?${params}` : ''}`, { replace: true });
    }, 350);
    return () => window.clearTimeout(timeout);
  }, [value, query, search, navigate]);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const params = new URLSearchParams(search);
    if (value.trim()) params.set('search', value.trim());
    else params.delete('search');
    navigate(`/catalog${params.size ? `?${params}` : ''}`, { replace: true });
    event.currentTarget.querySelector('input')?.blur();
  }
  return (
    <form className="rp-search" role="search" onSubmit={submit}>
      <button type="submit" aria-label="Найти товары">
        <Search size={21} strokeWidth={1.7} />
      </button>
      <input
        type="search"
        aria-label="Поиск товаров"
        placeholder="Поиск по магазину"
        value={value}
        maxLength={120}
        onChange={(event) => setValue(event.target.value)}
        enterKeyHint="search"
        autoComplete="off"
      />
      {value && (
        <button type="button" aria-label="Очистить поиск" onClick={() => setValue('')}>
          <X size={18} />
        </button>
      )}
      {onFilters && (
        <button type="button" aria-label="Категории и фильтры" onClick={onFilters}>
          <SlidersHorizontal size={20} strokeWidth={1.6} />
        </button>
      )}
    </form>
  );
}

export function Layout() {
  const { itemCount } = useCart();
  const { pathname } = useLocation();
  return (
    <div className="rp retail">
      <div className="rp-paper">
        <a className="skip-link" href="#main">
          К содержимому
        </a>
        <header className="rp-header">
          <Link className="rp-logo" to="/catalog" aria-label={`${STORE_BRAND} — главная`}>
            <img src="/brand-logo-original.png" alt="" width="52" height="52" />
          </Link>
          <Link className="rp-store" to="/about">
            <strong>{STORE_BRAND}</strong>
            <span>Севастополь, Камышовое шоссе, 25</span>
          </Link>
          <Link className="rp-store-arrow" aria-label="О нас" to="/about">
            <ChevronRight size={20} strokeWidth={1.6} />
          </Link>
        </header>
        <main id="main" className="rp-main">
          <Suspense
            fallback={
              <div className="route-loading" role="status" aria-label="Загрузка страницы">
                <span className="skeleton" />
                <span className="skeleton" />
              </div>
            }
          >
            <Outlet />
          </Suspense>
        </main>
        <nav className="rp-nav" aria-label="Основные разделы">
          {navigation.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              aria-label={to === '/cart' && itemCount ? `Корзина, позиций: ${itemCount}` : label}
              className={() =>
                (to === '/catalog' && pathname.startsWith('/product/')) ||
                (to === '/cart' && pathname.startsWith('/checkout'))
                  ? 'retail-nav-parent'
                  : ''
              }
            >
              <span className="rp-nav-icon">
                <Icon size={23} strokeWidth={1.6} />
                {to === '/cart' && itemCount > 0 && <b aria-hidden="true">{itemCount}</b>}
              </span>
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
