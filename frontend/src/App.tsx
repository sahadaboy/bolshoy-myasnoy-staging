import { lazy, useEffect, useLayoutEffect } from 'react';
import { ArrowLeft } from 'lucide-react';
import { Link, Navigate, Route, Routes, useLocation, useNavigationType } from 'react-router-dom';
import { Layout } from './components/Layout';
import { STORE_BRAND } from './data/brand';
import { useTelegram } from './hooks/useTelegram';

const CatalogPage = lazy(() =>
  import('./pages/CatalogPage').then((module) => ({
    default: module.CatalogPage,
  })),
);
const ProductPage = lazy(() =>
  import('./pages/ProductPage').then((module) => ({
    default: module.ProductPage,
  })),
);
const CartPage = lazy(() =>
  import('./pages/CartPage').then((module) => ({ default: module.CartPage })),
);
const IdeasPage = lazy(() => import('./pages/IdeasPage'));
const ArticlePage = lazy(() => import('./pages/ArticlePage'));
const ProfilePage = lazy(() => import('./pages/ProfilePage'));
const ProfileInfoPage = lazy(() => import('./pages/ProfileInfoPage'));
const CheckoutPage = lazy(() => import('./pages/CheckoutPage'));
const OrdersPage = lazy(() =>
  import('./pages/OrdersPage').then((module) => ({
    default: module.OrdersPage,
  })),
);
const OrderPage = lazy(() =>
  import('./pages/OrdersPage').then((module) => ({
    default: module.OrderPage,
  })),
);
const AboutPage = lazy(() => import('./pages/AboutPage'));
const StoreMapPage = lazy(() => import('./pages/StoreMapPage'));
const DinnerPage = lazy(() => import('./pages/DinnerPage'));
const scrollPositions = new Map<string, number>();

function ScrollMemory() {
  const location = useLocation();
  const action = useNavigationType();
  useLayoutEffect(() => {
    window.history.scrollRestoration = 'manual';
    const y = action === 'POP' ? scrollPositions.get(location.key) || 0 : 0;
    const frame = requestAnimationFrame(() => window.scrollTo({ top: y, behavior: 'instant' }));
    return () => {
      cancelAnimationFrame(frame);
      scrollPositions.set(location.key, window.scrollY);
      while (scrollPositions.size > 64)
        scrollPositions.delete(scrollPositions.keys().next().value!);
    };
  }, [location.key, action]);
  return null;
}

export default function App() {
  useTelegram();
  const { pathname } = useLocation();
  useEffect(() => {
    const title =
      pathname === '/about'
        ? 'О нас'
        : pathname === '/ideas/dinner'
          ? 'Идея для ужина'
          : pathname.startsWith('/cart')
            ? 'Корзина'
            : pathname.startsWith('/ideas')
              ? 'Идеи'
              : pathname.startsWith('/profile')
                ? 'Профиль'
                : pathname.startsWith('/product/')
                  ? 'Товар'
                  : 'Каталог';
    document.title = `${title} — ${STORE_BRAND}`;
  }, [pathname]);
  return (
    <>
      <ScrollMemory />
      <Routes>
        <Route path="design-preview" element={<Navigate to="/catalog" replace />} />
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/catalog" replace />} />
          <Route path="catalog" element={<CatalogPage />} />
          <Route path="product/:id" element={<ProductPage />} />
          <Route path="cart" element={<CartPage />} />
          <Route path="checkout" element={<CheckoutPage />} />
          <Route path="ideas" element={<IdeasPage />} />
          <Route path="ideas/dinner" element={<DinnerPage />} />
          <Route path="about" element={<AboutPage />} />
          <Route path="about/map" element={<StoreMapPage />} />
          <Route path="ideas/article/:slug" element={<ArticlePage />} />
          <Route path="ideas/recipes" element={<Navigate to="/ideas?kind=recipe" replace />} />
          <Route
            path="ideas/collections"
            element={<Navigate to="/ideas?kind=collection" replace />}
          />
          <Route path="profile" element={<ProfilePage />} />
          <Route path="profile/orders" element={<OrdersPage />} />
          <Route path="profile/orders/:id" element={<OrderPage />} />
          <Route path="profile/store" element={<Navigate to="/about" replace />} />
          <Route path="profile/about" element={<Navigate to="/about" replace />} />
          <Route path="profile/contacts" element={<Navigate to="/about" replace />} />
          <Route path="profile/:module" element={<ProfileInfoPage />} />
          <Route
            path="*"
            element={
              <div className="state-panel">
                <h1>Страница не найдена</h1>
                <p>Проверьте адрес или вернитесь в каталог.</p>
                <Link className="button button-primary" to="/catalog">
                  <ArrowLeft size={18} aria-hidden="true" /> В каталог
                </Link>
              </div>
            }
          />
        </Route>
      </Routes>
    </>
  );
}
