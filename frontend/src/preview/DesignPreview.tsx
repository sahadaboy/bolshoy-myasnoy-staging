import { useEffect, useRef, useState, type FormEvent } from 'react';
import {
  ArrowRight,
  BookOpen,
  ChevronRight,
  Grid2X2,
  ImageOff,
  MapPin,
  Minus,
  Plus,
  Search,
  ShoppingBasket,
  UserRound,
  X,
} from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  previewBanner,
  previewDepartments,
  previewCategoryList,
  previewProducts,
  stories,
  type PreviewProduct,
  type Story,
} from './previewData';
import './preview.css';

const money = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 });
const amount = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 3 });
const meals = ['Все идеи', 'Завтрак', 'Обед', 'Ужин'];

function ProductPhoto({ product }: { product: PreviewProduct }) {
  const [failed, setFailed] = useState(false);
  return product.image && !failed ? (
    <img
      src={product.image}
      alt={product.name}
      width="320"
      height="320"
      loading="lazy"
      onError={() => setFailed(true)}
    />
  ) : (
    <span className="rp-photo-empty">
      <ImageOff size={28} strokeWidth={1.3} />
      <span>Фото появится позже</span>
    </span>
  );
}

function Quantity({
  product,
  value,
  change,
}: {
  product: PreviewProduct;
  value: number;
  change: (id: number, delta: number) => void;
}) {
  return value > 0 ? (
    <div className="rp-quantity" aria-label={`Количество: ${product.name}`}>
      <button
        aria-label={`Уменьшить: ${product.name}`}
        onClick={() => change(product.id, -product.step)}
      >
        <Minus size={17} />
      </button>
      <output aria-live="polite">
        {amount.format(value)}
        {product.unit === 'kg' ? ' кг' : ''}
      </output>
      <button
        aria-label={`Добавить ещё: ${product.name}`}
        onClick={() => change(product.id, product.step)}
      >
        <Plus size={17} />
      </button>
    </div>
  ) : (
    <button
      className="rp-add"
      aria-label={`В корзину: ${product.name}`}
      onClick={() => change(product.id, product.step)}
    >
      <Plus size={22} strokeWidth={1.7} />
    </button>
  );
}

export default function DesignPreview() {
  const [params, setParams] = useSearchParams();
  const screen = params.get('screen') === 'ideas' ? 'ideas' : 'catalog';
  const department = params.get('department') || '';
  const query = params.get('q') || '';
  const [draft, setDraft] = useState(query);
  const [meal, setMeal] = useState('Все идеи');
  // Keep demonstration quantities out of the real CartProvider and localStorage.
  const [quantities, setQuantities] = useState<Record<number, number>>({});
  const [detail, setDetail] = useState<
    Story | PreviewProduct | 'store' | 'cart' | 'categories' | null
  >(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const shelf = useRef<HTMLElement>(null);
  const isFiltered = Boolean(department || query);
  const products = previewProducts.filter(
    (product) =>
      (!department || product.department === department) &&
      (!query || product.name.toLocaleLowerCase('ru').includes(query.toLocaleLowerCase('ru'))),
  );
  const visibleProducts = isFiltered ? products : products.filter((product) => product.featured);
  const cart = previewProducts.filter((product) => quantities[product.id] > 0);
  const total =
    cart.reduce(
      (sum, product) => sum + Math.round(product.price * quantities[product.id] * 100),
      0,
    ) / 100;
  const filteredStories = stories.filter(
    (story) => meal === 'Все идеи' || story.meals.includes(meal),
  );
  const feature = filteredStories.find((story) => story.featured) || filteredStories[0];

  useEffect(() => {
    setDraft(query);
  }, [query]);
  useEffect(() => {
    document.title = `${screen === 'ideas' ? 'Идеи' : 'Витрина'} · Preview — Большой Мясной`;
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [screen]);

  function browse(next: { screen?: string; department?: string; q?: string } = {}) {
    setParams(Object.fromEntries(Object.entries(next).filter(([, value]) => value)));
  }
  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    browse({ q: draft.trim() });
    event.currentTarget.querySelector('input')?.blur();
  }
  function change(id: number, delta: number) {
    const product = previewProducts.find((item) => item.id === id);
    if (!product) return;
    setQuantities((current) => {
      const previous = current[id] || 0;
      const minimum = product.minimum || product.step;
      const next =
        previous === 0 && delta > 0 ? minimum : Math.round((previous + delta) * 1000) / 1000;
      return { ...current, [id]: next < minimum ? 0 : next };
    });
  }
  function open(value: NonNullable<typeof detail>) {
    setDetail(value);
    dialog.current?.showModal();
  }
  function close() {
    dialog.current?.close();
  }
  const sectionTitle = query
    ? 'Результаты поиска'
    : previewDepartments.find((item) => item.id === department)?.name ||
      previewCategoryList.find((item) => item.id === department)?.name ||
      'К хорошему мясу';

  return (
    <div className="rp">
      <div className="rp-paper">
        <div className="rp-preview-note">
          Дизайн-превью <span>Демонстрационные материалы</span>
        </div>
        <header className="rp-header">
          <Link className="rp-logo" aria-label="Большой Мясной — главная" to="/design-preview">
            <img src="/brand-logo-original.png" alt="" width="52" height="52" />
          </Link>
          <button
            className="rp-store"
            onClick={() => open('store')}
            aria-label="Информация о магазине: Севастополь, Камышовое шоссе, 25"
          >
            <strong>Большой Мясной</strong>
            <span>Севастополь, Камышовое шоссе, 25</span>
          </button>
          <button className="rp-store-arrow" aria-label="О магазине" onClick={() => open('store')}>
            <ChevronRight size={20} strokeWidth={1.6} />
          </button>
        </header>
        <main className="rp-main">
          {screen === 'catalog' ? (
            <>
              <form className="rp-search" role="search" onSubmit={search}>
                <button type="submit" aria-label="Найти товары">
                  <Search size={21} strokeWidth={1.7} />
                </button>
                <input
                  type="search"
                  aria-label="Поиск товаров"
                  placeholder="Поиск по магазину"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  enterKeyHint="search"
                />
                {draft && (
                  <button
                    type="button"
                    aria-label="Очистить поиск"
                    onClick={() => {
                      setDraft('');
                      if (query) browse();
                    }}
                  >
                    <X size={18} />
                  </button>
                )}
              </form>
              <section className="rp-departments" aria-label="Категории товаров">
                <div className="rp-department-rail rp-primary-categories">
                  {previewDepartments.map((item) => (
                    <button
                      key={item.id}
                      onClick={() => browse({ department: item.id })}
                      aria-pressed={department === item.id}
                    >
                      <span className="rp-department-photo">
                        <img src={item.image} alt="" width="80" height="72" />
                      </span>
                      <span>{item.name}</span>
                    </button>
                  ))}
                </div>
                <button className="rp-all-categories" onClick={() => open('categories')}>
                  Посмотреть все категории <ChevronRight size={15} />
                </button>
              </section>
              {!isFiltered && (
                <a
                  className="rp-promo"
                  href="#rp-shelf"
                  onClick={(event) => {
                    event.preventDefault();
                    shelf.current?.scrollIntoView({
                      block: 'start',
                      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
                        ? 'instant'
                        : 'smooth',
                    });
                  }}
                  aria-label={previewBanner.alt_text}
                >
                  <img
                    src={previewBanner.image}
                    alt={previewBanner.alt_text}
                    width="1100"
                    height="500"
                    fetchPriority="high"
                  />
                </a>
              )}
              <section
                className="rp-shelf"
                id="rp-shelf"
                ref={shelf}
                aria-labelledby="rp-shelf-title"
              >
                <div className="rp-section-heading">
                  <h1 id="rp-shelf-title">{sectionTitle}</h1>
                  <Link to="/catalog">
                    Все товары <ChevronRight size={16} />
                  </Link>
                </div>
                {isFiltered && (
                  <div className="rp-filter-summary">
                    <span>
                      {query ? `По запросу «${query}»` : 'Товары демонстрационной витрины'}
                    </span>
                    <button onClick={() => browse()}>
                      Сбросить <X size={14} />
                    </button>
                  </div>
                )}
                {visibleProducts.length ? (
                  <div className="rp-products">
                    {visibleProducts.map((product) => (
                      <article className="rp-product" key={product.id}>
                        <button
                          className="rp-product-photo"
                          onClick={() => open(product)}
                          aria-label={`Подробнее: ${product.name}`}
                        >
                          <ProductPhoto product={product} />
                        </button>
                        <div
                          className={`rp-product-purchase${quantities[product.id] ? ' has-quantity' : ''}`}
                        >
                          <p className="rp-price">
                            {money.format(product.price)}{' '}
                            <span>₽/{product.unit === 'kg' ? 'кг' : 'шт'}</span>
                          </p>
                          <Quantity
                            product={product}
                            value={quantities[product.id] || 0}
                            change={change}
                          />
                        </div>
                        <button className="rp-product-name" onClick={() => open(product)}>
                          {product.name}
                        </button>
                        {product.size && <p className="rp-product-size">{product.size}</p>}
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="rp-empty">
                    <Search size={28} />
                    <h2>{query ? 'Ничего не нашлось' : 'Больше товаров в каталоге'}</h2>
                    <p>
                      {query
                        ? 'Попробуйте «горчица» или «кешью».'
                        : 'Для этой категории пока нет фотографий в preview.'}
                    </p>
                    <Link to="/catalog">
                      Открыть каталог <ArrowRight size={16} />
                    </Link>
                  </div>
                )}
                <p className="rp-data-note">Демонстрационная витрина · цены из каталога магазина</p>
              </section>
              {!isFiltered && (
                <section className="rp-home-ideas">
                  <div className="rp-section-heading">
                    <h2>Что приготовить?</h2>
                    <button onClick={() => browse({ screen: 'ideas' })}>
                      Все идеи <ChevronRight size={16} />
                    </button>
                  </div>
                  <button className="rp-home-story" onClick={() => browse({ screen: 'ideas' })}>
                    <img
                      src="/preview/family-dinner.webp"
                      alt="Запечённая курица с гарниром"
                      width="700"
                      height="400"
                      loading="lazy"
                    />
                    <span>
                      <strong>Собираемся за столом</strong>
                      <span>Вдохновение для большого обеда</span>
                    </span>
                    <ArrowRight size={20} />
                  </button>
                </section>
              )}
            </>
          ) : (
            <div className="rp-ideas">
              <div className="rp-ideas-title">
                <h1>Идеи</h1>
                <p>Вдохновение на каждый день</p>
              </div>
              <div className="rp-meals" aria-label="Тип приёма пищи">
                {meals.map((item) => (
                  <button key={item} aria-pressed={meal === item} onClick={() => setMeal(item)}>
                    {item}
                  </button>
                ))}
              </div>
              <section className="rp-topics" aria-labelledby="rp-topics-title">
                <h2 id="rp-topics-title">Собрали для вас</h2>
                <div className="rp-topic-rail">
                  {stories
                    .filter((story) => story.topic)
                    .map((story) => (
                      <button className="rp-topic" key={story.id} onClick={() => open(story)}>
                        <img src={story.image} alt="" width="280" height="220" />
                        <span>{story.title}</span>
                      </button>
                    ))}
                </div>
              </section>
              {feature && (
                <button className="rp-feature" onClick={() => open(feature)}>
                  <img src={feature.image} alt={feature.alt} width="720" height="430" />
                  <span className="rp-feature-copy">
                    <span className="rp-feature-kind">
                      {feature.recipe
                        ? 'Рецепт'
                        : feature.featured
                          ? 'Большой обед'
                          : 'На каждый день'}
                    </span>
                    <strong>{feature.title}</strong>
                    <span>{feature.description}</span>
                    <span className="rp-feature-arrow">
                      <ArrowRight size={20} />
                    </span>
                  </span>
                </button>
              )}
              <section className="rp-recipes" aria-labelledby="rp-recipes-title">
                <div className="rp-section-heading">
                  <h2 id="rp-recipes-title">Готовим дома</h2>
                  <button onClick={() => setMeal('Все идеи')}>
                    Все рецепты <ChevronRight size={16} />
                  </button>
                </div>
                <div className="rp-recipe-grid">
                  {filteredStories
                    .filter((story) => story.recipe)
                    .map((story) => (
                      <button className="rp-recipe" key={story.id} onClick={() => open(story)}>
                        <img
                          src={story.image}
                          alt={story.alt}
                          width="350"
                          height="290"
                          loading="lazy"
                        />
                        <strong>{story.title}</strong>
                        <span>{story.description}</span>
                      </button>
                    ))}
                </div>
              </section>
              <p className="rp-data-note">Демонстрационная редакционная подборка</p>
            </div>
          )}
        </main>
        <nav className="rp-nav" aria-label="Основные разделы">
          <Link to="/design-preview" aria-current={screen === 'catalog' ? 'page' : undefined}>
            <span className="rp-nav-icon">
              <Grid2X2 size={23} strokeWidth={1.6} />
            </span>
            <span>Каталог</span>
          </Link>
          <Link
            to="/design-preview?screen=ideas"
            aria-current={screen === 'ideas' ? 'page' : undefined}
          >
            <span className="rp-nav-icon">
              <BookOpen size={23} strokeWidth={1.6} />
            </span>
            <span>Идеи</span>
          </Link>
          <button
            onClick={() => open('cart')}
            aria-label={`Корзина${cart.length ? `, ${cart.length} позиций` : ''}`}
          >
            <span className="rp-nav-icon">
              <ShoppingBasket size={24} strokeWidth={1.6} />
              {cart.length > 0 && <b>{cart.length}</b>}
            </span>
            <span>Корзина</span>
          </button>
          <button onClick={() => open('store')}>
            <span className="rp-nav-icon">
              <UserRound size={24} strokeWidth={1.6} />
            </span>
            <span>Профиль</span>
          </button>
        </nav>
        <dialog
          className="rp-dialog"
          aria-label={
            typeof detail === 'string'
              ? detail === 'cart'
                ? 'Демонстрационная корзина'
                : detail === 'categories'
                  ? 'Все категории'
                  : 'О магазине'
              : detail && 'price' in detail
                ? detail.name
                : detail?.title || 'Просмотр'
          }
          ref={dialog}
          onClick={(event) => {
            if (event.target === event.currentTarget) close();
          }}
          onClose={() => setDetail(null)}
        >
          <button className="rp-dialog-close" autoFocus aria-label="Закрыть" onClick={close}>
            <X size={22} />
          </button>
          {detail === 'categories' ? (
            <div className="rp-store-detail">
              <h2>Все категории</h2>
              <div className="rp-category-list">
                {previewCategoryList.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => {
                      browse({ department: item.id });
                      close();
                    }}
                  >
                    <span>{item.name}</span>
                    <ChevronRight size={17} />
                  </button>
                ))}
              </div>
            </div>
          ) : detail === 'store' ? (
            <div className="rp-store-detail">
              <span className="rp-logo">
                <img src="/brand-logo-original.png" alt="" width="52" height="52" />
              </span>
              <h2>Большой Мясной</h2>
              <p>Всегда большой выбор хорошего мяса!</p>
              <div>
                <MapPin size={20} />
                <p>
                  Севастополь
                  <br />
                  <strong>Камышовое шоссе, 25</strong>
                </p>
              </div>
              <Link className="rp-primary" to="/profile" onClick={close}>
                Открыть профиль <ChevronRight size={18} />
              </Link>
            </div>
          ) : detail === 'cart' ? (
            <div className="rp-cart-detail">
              <h2>Корзина</h2>
              <p className="rp-dialog-note">Демонстрационная корзина preview</p>
              {cart.length ? (
                <>
                  {cart.map((product) => (
                    <div className="rp-cart-line" key={product.id}>
                      {product.image && <img src={product.image} alt="" width="64" height="64" />}
                      <div>
                        <strong>{product.name}</strong>
                        <p>
                          {money.format(product.price)} ₽/{product.unit === 'kg' ? 'кг' : 'шт'}
                        </p>
                        <Quantity
                          product={product}
                          value={quantities[product.id]}
                          change={change}
                        />
                      </div>
                    </div>
                  ))}
                  <div className="rp-cart-total">
                    <span>Итого</span>
                    <strong>{money.format(total)} ₽</strong>
                  </div>
                </>
              ) : (
                <div className="rp-empty">
                  <ShoppingBasket size={36} />
                  <h3>Выберите что-нибудь вкусное</h3>
                  <p>Товары из витрины появятся здесь.</p>
                  <button
                    className="rp-primary"
                    onClick={() => {
                      close();
                      browse();
                    }}
                  >
                    В витрину
                  </button>
                </div>
              )}
            </div>
          ) : detail && 'price' in detail ? (
            <div className="rp-product-detail">
              <div className="rp-detail-photo">
                <ProductPhoto product={detail} />
              </div>
              <p className="rp-dialog-note">Демонстрационная карточка</p>
              <h2>{detail.name}</h2>
              {detail.size && <p>{detail.size}</p>}
              <div className="rp-detail-purchase">
                <p className="rp-price">
                  {money.format(detail.price)} <span>₽/{detail.unit === 'kg' ? 'кг' : 'шт'}</span>
                </p>
                <Quantity product={detail} value={quantities[detail.id] || 0} change={change} />
              </div>
              <p className="rp-dialog-note">
                Цена из каталога магазина. Фотография для preview; привязки к реальным товарам не
                изменены.
              </p>
            </div>
          ) : detail && typeof detail !== 'string' ? (
            <article className="rp-story-detail">
              <img src={detail.image} alt={detail.alt} width="720" height="500" />
              <div>
                <p className="rp-dialog-note">Демонстрационный материал</p>
                <h2>{detail.title}</h2>
                <p>{detail.description}</p>
                <p>{detail.body}</p>
                <h3>Что понадобится</h3>
                <p>{detail.ingredients}</p>
                <button
                  className="rp-primary"
                  onClick={() => {
                    close();
                    browse();
                  }}
                >
                  Выбрать продукты <ArrowRight size={18} />
                </button>
              </div>
            </article>
          ) : null}
        </dialog>
      </div>
    </div>
  );
}
