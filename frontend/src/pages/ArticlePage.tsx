import { useCallback, useState } from 'react';
import { Clock3, Plus, UsersRound } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { fetchArticle } from '../lib/api';
import { useResource } from '../hooks/useResource';
import { useCart } from '../context/CartContext';
import { quantityThousandths } from '../lib/quantity';
import { BackLink } from '../components/Retail';
import { EditorialImage, RecipeCard } from '../components/RecipeCard';
import { ErrorState, LoadingGrid } from '../components/States';

export default function ArticlePage() {
  const { slug = '' } = useParams();
  const load = useCallback((signal: AbortSignal) => fetchArticle(slug, signal), [slug]);
  const { data, loading, error, retry } = useResource(load);
  const cart = useCart();
  const [notice, setNotice] = useState('');
  const linked =
    data?.ingredients.filter((item) => item.product?.is_available && item.cart_quantity) || [];
  return (
    <>
      <BackLink fallback="/ideas" />
      {loading ? (
        <LoadingGrid count={2} />
      ) : error || !data || data.is_demo ? (
        <ErrorState retry={retry} message={error || 'Материал не найден.'} />
      ) : (
        <article className="retail-article">
          {data.image && (
            <div className="retail-article-cover">
              <EditorialImage article={data} />
            </div>
          )}
          <h1>{data.title}</h1>
          {data.description && <p className="retail-article-description">{data.description}</p>}
          {(data.duration_minutes || data.servings) && (
            <div className="retail-article-meta">
              {data.duration_minutes && (
                <span>
                  <Clock3 size={17} />
                  {data.duration_minutes} мин
                </span>
              )}
              {data.servings && (
                <span>
                  <UsersRound size={17} />
                  {data.servings} порц.
                </span>
              )}
            </div>
          )}
          {data.body && <p className="retail-article-body">{data.body}</p>}
          {data.ingredients.length > 0 && (
            <section>
              <h2>Ингредиенты</h2>
              <ul className="retail-ingredients">
                {data.ingredients.map((item) => (
                  <li key={item.id}>
                    <div>
                      <strong>{item.name}</strong>
                      <span>{item.amount}</span>
                      {item.product && (
                        <Link to={`/product/${item.product.id}`}>{item.product.name}</Link>
                      )}
                    </div>
                    {item.product && item.cart_quantity ? (
                      <button
                        className="rp-add"
                        aria-label={`Добавить ингредиент ${item.name}`}
                        onClick={() =>
                          setNotice(
                            cart.add(item.product!, quantityThousandths(item.cart_quantity!))
                              ? `${item.name}: добавлено в корзину`
                              : 'Не удалось добавить это количество. Проверьте товар в каталоге.',
                          )
                        }
                      >
                        <Plus size={20} />
                      </button>
                    ) : item.product && !item.product.is_available ? (
                      <span className="retail-unavailable">Нет в наличии</span>
                    ) : null}
                  </li>
                ))}
              </ul>
              {linked.length > 0 && (
                <button
                  className="button button-secondary"
                  onClick={() => {
                    const added = linked.filter((item) =>
                      cart.add(item.product!, quantityThousandths(item.cart_quantity!)),
                    ).length;
                    setNotice(`Добавлено ингредиентов: ${added} из ${linked.length}`);
                  }}
                >
                  Добавить доступные ингредиенты
                </button>
              )}
              <p role="status" className="retail-subtitle">
                {notice}
              </p>
            </section>
          )}
          {data.steps.length > 0 && (
            <section>
              <h2>Как приготовить</h2>
              <ol className="retail-steps">
                {data.steps.map((step, index) => (
                  <li key={index}>
                    <span>{index + 1}</span>
                    <p>{step}</p>
                  </li>
                ))}
              </ol>
            </section>
          )}
          {data.recipes.length > 0 && (
            <section>
              <h2>В этой подборке</h2>
              <div className="rp-recipe-grid">
                {data.recipes.map((article) => (
                  <RecipeCard key={article.id} article={article} />
                ))}
              </div>
            </section>
          )}
          <Link className="button button-secondary" to="/ideas">
            Все идеи
          </Link>
        </article>
      )}
    </>
  );
}
