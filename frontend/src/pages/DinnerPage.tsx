import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Check, ChevronLeft, Clock3, CookingPot, ShoppingBasket, UsersRound } from 'lucide-react';
import { Link } from 'react-router-dom';
import { BackLink } from '../components/Retail';
import { ErrorState, LoadingGrid } from '../components/States';
import { QuantityControl } from '../components/QuantityControl';
import { useResource } from '../hooks/useResource';
import { useCart } from '../context/CartContext';
import { fetchDinnerSchema, prepareDinner, suggestDinner } from '../lib/api';
import {
  formatMoney,
  lineTotal,
  minQuantity,
  quantityThousandths,
  stepQuantity,
} from '../lib/quantity';
import type { DinnerAnswers, DinnerIdea } from '../types';

const initialAnswers: DinnerAnswers = { servings: 2, pantry: [], exclude: [], answers: {} };

export default function DinnerPage() {
  const resource = useResource(fetchDinnerSchema);
  const [answers, setAnswers] = useState<DinnerAnswers>(initialAnswers);
  const [step, setStep] = useState(0);
  const [search, setSearch] = useState('');
  const [results, setResults] = useState<DinnerIdea[] | null>(null);
  const [selected, setSelected] = useState<DinnerIdea | null>(null);
  const [quantities, setQuantities] = useState<Record<number, number>>({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [added, setAdded] = useState(false);
  const initialized = useRef(false);
  const pending = useRef<AbortController | null>(null);
  const legend = useRef<HTMLLegendElement>(null);
  const cart = useCart();
  const schema = resource.data;
  const question = schema?.questions[step];

  useEffect(() => {
    if (!schema || initialized.current) return;
    initialized.current = true;
    const defaults: Record<string, number[]> = {};
    for (const item of schema.questions) {
      if (item.key !== 'preferences') {
        const any = item.options.find((option) => option.is_any);
        if (any) defaults[item.key] = [any.id];
      }
    }
    setAnswers({ servings: schema.default_servings, pantry: [], exclude: [], answers: defaults });
  }, [schema]);
  useEffect(() => () => pending.current?.abort(), []);
  useEffect(() => {
    legend.current?.focus({ preventScroll: true });
  }, [step, schema]);

  const choices =
    question?.key === 'pantry'
      ? answers.pantry
      : question?.key === 'exclude'
        ? answers.exclude
        : answers.answers[question?.key || ''] || [];
  const single = question?.key === 'dish' || question?.key === 'spice';
  const ready =
    question?.key === 'servings'
      ? Number.isInteger(answers.servings) &&
        answers.servings >= 1 &&
        answers.servings <= (schema?.max_servings || 12)
      : !question?.required || choices.length > 0;

  function toggle(id: number) {
    if (!question) return;
    const next = single
      ? [id]
      : choices.includes(id)
        ? choices.filter((value) => value !== id)
        : [...choices, id];
    setAnswers((previous) =>
      question.key === 'pantry' || question.key === 'exclude'
        ? { ...previous, [question.key]: next }
        : { ...previous, answers: { ...previous.answers, [question.key]: next } },
    );
  }
  function goTo(next: number) {
    setStep(next);
    setSearch('');
    setError('');
    window.scrollTo({ top: 0, behavior: 'instant' });
  }
  async function findIdeas(event?: FormEvent) {
    event?.preventDefault();
    if (!ready || pending.current) return;
    if (schema && step < schema.questions.length - 1) {
      goTo(step + 1);
      return;
    }
    const controller = new AbortController();
    pending.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 30000);
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const response = await suggestDinner(answers, controller.signal);
      if (controller.signal.aborted) return;
      setResults(response.results);
      setSelected(null);
      window.scrollTo({ top: 0, behavior: 'instant' });
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Не удалось подобрать блюда. Попробуйте ещё раз.',
      );
    } finally {
      window.clearTimeout(timeout);
      pending.current = null;
      setBusy(false);
    }
  }
  function choose(idea: DinnerIdea) {
    setSelected(idea);
    setQuantities(
      Object.fromEntries(
        idea.shopping.map((item) => [item.product.id, quantityThousandths(item.quantity)]),
      ),
    );
    setAdded(false);
    setNotice('');
    setError('');
    window.scrollTo({ top: 0, behavior: 'instant' });
  }
  function editAnswers() {
    setResults(null);
    setSelected(null);
    setNotice('');
    setError('');
    goTo(0);
  }
  function restart() {
    initialized.current = false;
    editAnswers();
    resource.retry();
  }
  const total =
    selected?.shopping.reduce(
      (sum, item) => sum + lineTotal(item.product, quantities[item.product.id] || 0),
      0,
    ) || 0;
  const toBuy = selected?.shopping.filter((item) => quantities[item.product.id] > 0) || [];

  async function addToCart() {
    if (!selected || !toBuy.length || added || pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 30000);
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const response = await prepareDinner(
        {
          ...answers,
          recipe_id: selected.id,
          items: toBuy.map((item) => ({
            product_id: item.product.id,
            quantity: (quantities[item.product.id] / 1000).toFixed(3),
            expected_price: item.product.price,
          })),
        },
        controller.signal,
      );
      if (controller.signal.aborted) return;
      if (response.prices_changed) {
        const latest = new Map(response.items.map((item) => [item.product.id, item.product]));
        setSelected({
          ...selected,
          shopping: selected.shopping.map((item) => ({
            ...item,
            product: latest.get(item.product.id) || item.product,
          })),
        });
        setNotice('Цены обновились. Проверьте сумму и нажмите «Добавить в корзину» ещё раз.');
        return;
      }
      if (
        !cart.addMany(
          response.items.map((item) => ({
            product: item.product,
            quantity: quantityThousandths(item.quantity),
          })),
        )
      ) {
        setError(
          'Не удалось совместить количество с товарами в корзине. Проверьте корзину и попробуйте ещё раз.',
        );
        return;
      }
      setAdded(true);
      setNotice('Список покупок добавлен в корзину.');
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : 'Проверьте список покупок и попробуйте ещё раз.',
      );
    } finally {
      window.clearTimeout(timeout);
      pending.current = null;
      setBusy(false);
    }
  }

  return (
    <>
      <BackLink fallback="/ideas" />
      <div className="page-intro">
        <h1>{schema?.title || 'Собрать идею для ужина'}</h1>
        {results === null && <p>{schema?.description}</p>}
      </div>
      {resource.loading ? (
        <LoadingGrid count={2} />
      ) : resource.error || !schema ? (
        <ErrorState
          retry={resource.retry}
          message={resource.error || 'Не удалось открыть подбор ужина.'}
        />
      ) : results === null ? (
        <form className="retail-dinner-form" onSubmit={findIdeas}>
          {question ? (
            <>
              <p className="retail-question-progress">
                Вопрос {step + 1} из {schema.questions.length}
              </p>
              <fieldset disabled={busy}>
                <legend ref={legend} tabIndex={-1}>
                  {question.title}
                </legend>
                {question.help_text && <p className="retail-subtitle">{question.help_text}</p>}
                {question.key === 'servings' ? (
                  <label className="retail-servings">
                    Человек
                    <input
                      type="number"
                      min="1"
                      max={schema.max_servings}
                      step="1"
                      value={answers.servings || ''}
                      onChange={(event) =>
                        setAnswers({ ...answers, servings: Number(event.target.value) })
                      }
                      required
                    />
                  </label>
                ) : (
                  <>
                    {(question.key === 'pantry' || question.key === 'exclude') && (
                      <input
                        className="retail-ingredient-search"
                        type="search"
                        value={search}
                        aria-label="Найти ингредиент"
                        placeholder="Найти продукт"
                        onChange={(event) => setSearch(event.target.value)}
                      />
                    )}
                    <div className="retail-answer-list">
                      {(question.key === 'pantry' || question.key === 'exclude'
                        ? schema.ingredients.filter((item) =>
                            item.name
                              .toLocaleLowerCase('ru')
                              .includes(search.toLocaleLowerCase('ru')),
                          )
                        : question.options
                      ).map((item) => (
                        <label
                          key={item.id}
                          className={choices.includes(item.id) ? 'is-selected' : ''}
                        >
                          <input
                            type={single ? 'radio' : 'checkbox'}
                            name={question.key}
                            checked={choices.includes(item.id)}
                            onChange={() => toggle(item.id)}
                          />
                          <span>{'label' in item ? item.label : item.name}</span>
                        </label>
                      ))}
                    </div>
                    {(question.key === 'pantry' || question.key === 'exclude') &&
                      !question.required && (
                        <p className="retail-subtitle">Можно ничего не выбирать.</p>
                      )}
                  </>
                )}
              </fieldset>
            </>
          ) : (
            <p>Подберём ужин из доступных продуктов магазина.</p>
          )}
          <div className="retail-question-actions">
            {step > 0 && (
              <button
                type="button"
                className="button button-secondary"
                disabled={busy}
                onClick={() => goTo(step - 1)}
              >
                <ChevronLeft size={17} /> Назад
              </button>
            )}
            <button className="button button-primary" type="submit" disabled={busy || !ready}>
              {busy
                ? 'Подбираем…'
                : step < schema.questions.length - 1
                  ? 'Далее'
                  : 'Подобрать ужин'}
            </button>
          </div>
        </form>
      ) : selected ? (
        <article className="retail-dinner-result">
          <button
            className="retail-text-link"
            disabled={busy}
            onClick={() => {
              setSelected(null);
              setNotice('');
              setError('');
            }}
          >
            <ChevronLeft size={16} /> Другие варианты
          </button>
          <h2>{selected.title}</h2>
          <p>{selected.description}</p>
          <div className="retail-article-meta">
            <span>
              <UsersRound size={17} />
              {selected.servings} порц.
            </span>
            {selected.duration_minutes && (
              <span>
                <Clock3 size={17} />
                {selected.duration_minutes} мин
              </span>
            )}
          </div>
          <section>
            <h3>Состав блюда</h3>
            <ul className="retail-dinner-composition">
              {selected.ingredients.map((item) => (
                <li key={item.id}>
                  <span>
                    {item.name}
                    {item.amount && <small>{item.amount}</small>}
                  </span>
                  <span className={item.have ? '' : 'needs-shopping'}>
                    {item.have ? (
                      <>
                        <Check size={15} /> Есть дома
                      </>
                    ) : item.status === 'buy' ? (
                      'Докупить'
                    ) : (
                      'По желанию'
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h3>Что докупить</h3>
            {selected.shopping.length ? (
              <>
                <div className="retail-dinner-shopping">
                  {selected.shopping.map((item) => {
                    const quantity = quantities[item.product.id] || 0;
                    return (
                      <div key={item.product.id} className={quantity ? '' : 'is-removed'}>
                        <label>
                          <input
                            type="checkbox"
                            checked={quantity > 0}
                            disabled={busy || added}
                            onChange={() =>
                              setQuantities({
                                ...quantities,
                                [item.product.id]: quantity
                                  ? 0
                                  : quantityThousandths(item.quantity),
                              })
                            }
                          />
                          <span>
                            {item.product.name}
                            <small>{formatMoney(lineTotal(item.product, quantity))}</small>
                          </span>
                        </label>
                        {quantity > 0 && (
                          <QuantityControl
                            product={item.product}
                            quantity={quantity}
                            disabled={busy || added}
                            onDecrease={() =>
                              setQuantities({
                                ...quantities,
                                [item.product.id]:
                                  quantity <= minQuantity(item.product)
                                    ? 0
                                    : quantity - stepQuantity(item.product),
                              })
                            }
                            onIncrease={() =>
                              setQuantities({
                                ...quantities,
                                [item.product.id]: quantity + stepQuantity(item.product),
                              })
                            }
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
                <div className="retail-dinner-total">
                  <span>К покупке</span>
                  <strong>{formatMoney(total)}</strong>
                </div>
                <button
                  className="button button-primary"
                  disabled={busy || added || !toBuy.length}
                  onClick={addToCart}
                >
                  <ShoppingBasket size={18} />
                  {busy
                    ? 'Проверяем товары…'
                    : added
                      ? 'Добавлено в корзину'
                      : 'Добавить в корзину'}
                </button>
              </>
            ) : (
              <p>Все необходимые продукты уже есть дома.</p>
            )}
            {added && (
              <Link className="button button-secondary" to="/cart">
                Перейти в корзину
              </Link>
            )}
          </section>
          <section>
            <h3>Как приготовить</h3>
            <ol className="retail-steps">
              {selected.steps.map((text, index) => (
                <li key={index}>
                  <span>{index + 1}</span>
                  <p>{text}</p>
                </li>
              ))}
            </ol>
          </section>
          <Link className="retail-text-link" to={`/ideas/article/${selected.slug}`}>
            Открыть рецепт
          </Link>
        </article>
      ) : (
        <section className="retail-dinner-ideas">
          <button className="retail-text-link" onClick={editAnswers}>
            Изменить ответы
          </button>
          <h2>{results.length ? 'Что приготовим сегодня?' : 'Подходящих блюд не нашлось'}</h2>
          {!results.length && (
            <p>
              Сейчас нет блюд из доступных товаров, которые подходят под ваши ответы. Попробуйте
              изменить предпочтения или исключения.
            </p>
          )}
          {results.map((idea) => (
            <article key={idea.id}>
              <CookingPot size={24} strokeWidth={1.5} />
              <h3>{idea.title}</h3>
              <p>{idea.description}</p>
              <div className="retail-article-meta">
                <span>{idea.servings} порц.</span>
                {idea.duration_minutes && <span>{idea.duration_minutes} мин</span>}
                {idea.owned_count > 0 && <span>Есть дома: {idea.owned_count}</span>}
              </div>
              <button className="button button-secondary" onClick={() => choose(idea)}>
                Выбрать идею
              </button>
            </article>
          ))}
        </section>
      )}
      {error && (
        <>
          <p role="alert" className="retail-dinner-error">
            {error}
          </p>
          <button className="retail-text-link" disabled={busy} onClick={restart}>
            Начать подбор заново
          </button>
        </>
      )}
      <p className="retail-dinner-notice" role="status">
        {notice}
      </p>
    </>
  );
}
