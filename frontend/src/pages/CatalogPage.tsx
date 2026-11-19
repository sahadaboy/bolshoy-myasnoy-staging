import { useEffect, useRef } from 'react';
import { ChevronRight, LayoutGrid, X } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { useCategories, useProducts } from '../hooks/useCatalog';
import { useResource } from '../hooks/useResource';
import { useCart } from '../context/CartContext';
import { fetchIdeas, fetchStorefront, productImageUrl } from '../lib/api';
import { ProductCard } from '../components/ProductCard';
import { EmptyState, ErrorState, LoadingGrid } from '../components/States';
import { SectionHeader, Sheet } from '../components/Retail';
import { SearchForm } from '../components/Layout';
import { productWord } from '../lib/text';
import { RecipeCard } from '../components/RecipeCard';
import { DinnerInvite } from '../components/DinnerInvite';

import { primaryCategories } from '../data/primaryCategories';
export function CatalogPage() {
  const [params, setParams] = useSearchParams();
  const category = params.get('category') || '';
  const categoryGroup = params.get('category_group') || '';
  const search = params.get('search') || '';
  const collection = params.get('collection') || '';
  const unit = params.get('unit') || '';
  const available = params.get('available') === '1';
  const ordering = params.get('ordering') || '';
  const home =
    !category &&
    !categoryGroup &&
    !search &&
    !collection &&
    !params.has('all') &&
    !unit &&
    !available &&
    !ordering;
  const categories = useCategories();
  const showcase = useResource(fetchStorefront);
  const data = useProducts(
    { category, categoryGroup, search, unit, available, ordering, collection },
    !home,
  );
  const { syncProducts } = useCart();
  const sheet = useRef<HTMLDialogElement>(null);
  const selected = categories.categories.find((item) => String(item.id) === category);
  const selectedGroup = primaryCategories.find((item) => item.id === categoryGroup);
  const children = categories.categories.filter(
    (item) => item.parent_id && String(item.parent_id) === category,
  );
  useEffect(() => {
    syncProducts(data.products);
  }, [data.products, syncProducts]);
  useEffect(() => {
    if (showcase.data) syncProducts(showcase.data.collections.flatMap((item) => item.products));
  }, [showcase.data, syncProducts]);
  function update(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key === 'category' || key === 'category_group') {
      next.delete('collection');
      next.delete(key === 'category' ? 'category_group' : 'category');
    }
    setParams(next);
    window.scrollTo({ top: 0, behavior: 'instant' });
  }
  function selectCategory(id: string) {
    update('category', id);
    sheet.current?.close();
  }
  return (
    <>
      <SearchForm onFilters={() => sheet.current?.showModal()} />
      <section className="rp-departments" aria-label="Категории товаров">
        <div className="rp-department-rail rp-primary-categories">
          {primaryCategories.map((item) => (
            <button
              key={item.id}
              aria-label={item.name}
              aria-pressed={categoryGroup === item.id}
              onClick={() => update('category_group', item.id)}
            >
              <span className="rp-department-photo">
                <img src={item.image} alt="" width="80" height="72" />
              </span>
              <span>{item.id === 'seafood' ? <>Море&shy;продукты</> : item.name}</span>
            </button>
          ))}
          <button aria-label="Все категории" onClick={() => sheet.current?.showModal()}>
            <span className="rp-department-photo retail-all-category-icon">
              <LayoutGrid size={28} strokeWidth={1.6} />
            </span>
            <span>Все категории</span>
          </button>
        </div>
      </section>
      {categories.error && (
        <ErrorState compact retry={categories.retry} message={categories.error} />
      )}
      {home ? (
        <>
          <h1 className="sr-only">Каталог Большого Мясного</h1>
          {showcase.loading ? (
            <LoadingGrid count={2} />
          ) : showcase.error ? (
            <ErrorState retry={showcase.retry} message={showcase.error} />
          ) : (
            <>
              {showcase.data?.banners.length ? (
                <section className="retail-banners" aria-label="Витрина магазина">
                  {showcase.data.banners.map((banner, index) => (
                    <Link key={banner.id} className="rp-promo" to={banner.target_url}>
                      <img
                        src={productImageUrl(banner.image) || ''}
                        alt={banner.alt_text}
                        width="1100"
                        height="500"
                        loading={index ? 'lazy' : 'eager'}
                        fetchPriority={index ? 'auto' : 'high'}
                      />
                    </Link>
                  ))}
                </section>
              ) : null}
              {showcase.data?.collections.map((item) => (
                <section className="rp-shelf" key={item.id}>
                  <SectionHeader
                    title={item.title}
                    to={`/catalog?collection=${item.slug}`}
                    actionLabel="Смотреть всё"
                  />
                  <div className="rp-products retail-showcase">
                    {item.products.map((product) => (
                      <ProductCard product={product} key={product.id} />
                    ))}
                  </div>
                </section>
              ))}
              {showcase.data?.dinner_enabled && <DinnerInvite />}
            </>
          )}
          <HomeIdeasTeaser />
        </>
      ) : (
        <section className="rp-shelf" aria-labelledby="catalog-title">
          <div className="rp-section-heading">
            <h1 id="catalog-title">
              {search
                ? 'Результаты поиска'
                : selected?.name ||
                  selectedGroup?.name ||
                  (collection
                    ? showcase.data?.collections.find((item) => item.slug === collection)?.title ||
                      'Подборка'
                    : 'Все товары')}
            </h1>
            <button onClick={() => sheet.current?.showModal()}>Фильтры</button>
          </div>
          <div className="retail-results">
            <span role="status">
              {data.loading
                ? 'Загружаем…'
                : `${data.count.toLocaleString('ru-RU')} ${productWord(data.count)}`}
              {search ? ` по запросу «${search}»` : ''}
            </span>
            <button onClick={() => setParams({ all: '1' })}>
              Сбросить <X size={13} />
            </button>
          </div>
          {children.length > 0 && (
            <div className="retail-chips">
              {children.map((item) => (
                <button key={item.id} onClick={() => selectCategory(String(item.id))}>
                  {item.name}
                </button>
              ))}
            </div>
          )}
          {data.loading ? (
            <LoadingGrid />
          ) : !data.products.length ? (
            data.error ? (
              <ErrorState retry={data.retry} message={data.error} />
            ) : (
              <EmptyState reset={() => setParams({ all: '1' })} />
            )
          ) : (
            <>
              <div className="rp-products">
                {data.products.map((product) => (
                  <ProductCard key={product.id} product={product} />
                ))}
              </div>
              {data.error && <ErrorState compact retry={data.loadMore} message={data.error} />}
              {data.hasMore && (
                <div className="load-more">
                  <button
                    className="button button-secondary"
                    disabled={data.loadingMore}
                    onClick={data.loadMore}
                  >
                    {data.loadingMore ? 'Загружаем…' : 'Показать ещё'}
                  </button>
                  <span>
                    Показано {data.products.length} из {data.count.toLocaleString('ru-RU')}
                  </span>
                </div>
              )}
            </>
          )}
        </section>
      )}
      <Sheet reference={sheet} title="Категории и фильтры">
        <Link
          className="button button-secondary"
          to="/catalog?all=1"
          onClick={() => sheet.current?.close()}
        >
          Все товары
        </Link>
        <h3>Все категории</h3>
        <div className="rp-category-list">
          {categories.categories.map((item) => (
            <button
              key={item.id}
              aria-pressed={category === String(item.id)}
              onClick={() => selectCategory(String(item.id))}
            >
              <span>{item.name}</span>
              <ChevronRight size={17} />
            </button>
          ))}
        </div>
        <h3>Фильтры</h3>
        <div className="retail-filter-fields">
          <label>
            Сортировка
            <select value={ordering} onChange={(event) => update('ordering', event.target.value)}>
              <option value="">По названию</option>
              <option value="price">Сначала дешевле</option>
              <option value="-price">Сначала дороже</option>
            </select>
          </label>
          <label>
            Единица продажи
            <select value={unit} onChange={(event) => update('unit', event.target.value)}>
              <option value="">Все товары</option>
              <option value="kg">На вес</option>
              <option value="pcs">Поштучно</option>
            </select>
          </label>
          <label className="retail-check">
            <input
              type="checkbox"
              checked={available}
              onChange={(event) => update('available', event.target.checked ? '1' : '')}
            />
            Доступные для заявки
          </label>
        </div>
        <button className="button button-primary" onClick={() => sheet.current?.close()}>
          Показать товары
        </button>
      </Sheet>
    </>
  );
}

const loadHomeIdeas = (signal: AbortSignal) => fetchIdeas(new URLSearchParams(), signal);
function HomeIdeasTeaser() {
  const { data } = useResource(loadHomeIdeas);
  const articles = data?.results.filter((item) => !item.is_demo) || [];
  const article = articles.find((item) => item.is_featured) || articles[0];
  return article ? (
    <section className="rp-home-ideas">
      <SectionHeader title="Что приготовить?" to="/ideas" actionLabel="Все идеи" />
      <RecipeCard article={article} variant="feature" />
    </section>
  ) : null;
}
