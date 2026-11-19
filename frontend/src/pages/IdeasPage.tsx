import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { fetchIdeas } from '../lib/api';
import { useResource } from '../hooks/useResource';
import { ErrorState, LoadingGrid } from '../components/States';
import { RecipeCard } from '../components/RecipeCard';
import { SectionHeader } from '../components/Retail';
import { DinnerInvite } from '../components/DinnerInvite';
import { MeatGuideInvite } from '../components/MeatGuideInvite';

const meals = [
  { id: '', title: 'Все идеи' },
  { id: 'breakfast', title: 'Завтрак' },
  { id: 'lunch', title: 'Обед' },
  { id: 'dinner', title: 'Ужин' },
];
export default function IdeasPage() {
  const [params, setParams] = useSearchParams();
  const meal = params.get('meal') || '';
  const kind = params.get('kind') || '';
  const page = params.get('page') || '';
  const category = params.get('category') || '';
  const load = useCallback(
    (signal: AbortSignal) =>
      fetchIdeas(
        new URLSearchParams(
          Object.fromEntries(
            Object.entries({ meal, kind, page, category }).filter(([, value]) => value),
          ),
        ),
        signal,
      ),
    [meal, kind, page, category],
  );
  const resource = useResource(load);
  const articles = (resource.data?.results || []).filter((article) => !article.is_demo);
  const feature =
    articles.find((article) => article.is_featured) ||
    articles.find((article) => article.kind === 'recipe');
  function filter(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (key === 'meal') next.delete('kind');
    if (key === 'kind') next.delete('meal');
    next.delete('page');
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  }
  return (
    <div className="rp-ideas">
      <div className="rp-ideas-title">
        <h1>Идеи</h1>
        <p>Вдохновение на каждый день</p>
      </div>
      {resource.data?.dinner_enabled && <DinnerInvite />}
      <MeatGuideInvite />
      <div className="rp-meals" aria-label="Тип приёма пищи">
        {meals.map((item) => (
          <button
            key={item.id}
            aria-pressed={meal === item.id && !kind}
            onClick={() => (item.id ? filter('meal', item.id) : setParams({}))}
          >
            {item.title}
          </button>
        ))}
        <button
          aria-pressed={kind === 'collection'}
          onClick={() => filter('kind', kind === 'collection' ? '' : 'collection')}
        >
          Подборки
        </button>
        <button
          aria-pressed={kind === 'recipe'}
          onClick={() => filter('kind', kind === 'recipe' ? '' : 'recipe')}
        >
          Рецепты
        </button>
      </div>
      {resource.data && resource.data.categories.length > 1 && (
        <div className="retail-chips" aria-label="Разделы идей">
          <button aria-pressed={!category} onClick={() => filter('category', '')}>
            Все разделы
          </button>
          {resource.data.categories.map((item) => (
            <button
              key={item.slug}
              aria-pressed={category === item.slug}
              onClick={() => filter('category', item.slug)}
            >
              {item.name}
            </button>
          ))}
        </div>
      )}
      {resource.loading ? (
        <LoadingGrid count={2} />
      ) : resource.error ? (
        <ErrorState retry={resource.retry} message={resource.error} />
      ) : !articles.length ? (
        <div className="rp-empty">
          <h2>Здесь появятся новые идеи</h2>
          <p>
            {meal || kind || category
              ? 'Попробуйте выбрать другой раздел.'
              : 'Подходящих идей не нашлось. Попробуйте собрать свой ужин.'}
          </p>
          {(meal || kind || category) && (
            <button className="button button-secondary" onClick={() => setParams({})}>
              Все идеи
            </button>
          )}
        </div>
      ) : (
        <>
          {articles.some((article) => article.is_topic) && kind !== 'recipe' && (
            <section className="rp-topics">
              <h2>Собрали для вас</h2>
              <div className="rp-topic-rail">
                {articles
                  .filter((article) => article.is_topic)
                  .map((article) => (
                    <RecipeCard key={article.id} article={article} variant="topic" />
                  ))}
              </div>
            </section>
          )}
          {feature && <RecipeCard article={feature} variant="feature" />}
          {articles.some((article) => article.kind === 'recipe' && article.id !== feature?.id) && (
            <section className="rp-recipes">
              <SectionHeader
                title="Готовим дома"
                action={() => filter('kind', 'recipe')}
                actionLabel="Все рецепты"
              />
              <div className="rp-recipe-grid">
                {articles
                  .filter((article) => article.kind === 'recipe' && article.id !== feature?.id)
                  .map((article) => (
                    <RecipeCard key={article.id} article={article} />
                  ))}
              </div>
            </section>
          )}
          {resource.data && (resource.data.next || resource.data.previous) && (
            <div className="retail-pagination">
              {resource.data.previous && (
                <button
                  className="button button-secondary"
                  onClick={() => filter('page', String(Math.max(1, Number(page || 1) - 1)))}
                >
                  Предыдущие
                </button>
              )}
              {resource.data.next && (
                <button
                  className="button button-secondary"
                  onClick={() => filter('page', String(Number(page || 1) + 1))}
                >
                  Ещё материалы
                </button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
