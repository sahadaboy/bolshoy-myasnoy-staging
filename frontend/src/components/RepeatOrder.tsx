import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { repeatOrder, type RepeatPreview } from '../lib/api';
import { useCart } from '../context/CartContext';
import { formatMoney, lineTotal, formatQuantity, quantityThousandths } from '../lib/quantity';

export function RepeatOrder({ id }: { id: string }) {
  const [preview, setPreview] = useState<RepeatPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [added, setAdded] = useState(false);
  const [notice, setNotice] = useState('');
  const pending = useRef(false);
  const cart = useCart();
  async function prepare(confirm: boolean) {
    if (pending.current || added) return;
    pending.current = true;
    setBusy(true);
    setNotice('');
    try {
      const next = await repeatOrder(id);
      setPreview(next);
      if (confirm && JSON.stringify(next.items) === JSON.stringify(preview?.items)) {
        if (!next.items.length) return;
        if (
          cart.addMany(
            next.items.map((item) => ({
              product: item.product,
              quantity: quantityThousandths(item.quantity),
            })),
          )
        ) {
          setAdded(true);
          setNotice('Товары добавлены в текущую корзину.');
        } else setNotice('Проверьте количество этих товаров в текущей корзине.');
      } else if (confirm)
        setNotice('Цены или состав изменились. Проверьте список перед добавлением.');
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : 'Не удалось проверить товары.');
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <section className="customer-repeat">
      <h2>Купить снова</h2>
      {!preview ? (
        <button className="button button-secondary" disabled={busy} onClick={() => prepare(false)}>
          {busy ? 'Проверяем товары…' : 'Повторить заказ'}
        </button>
      ) : (
        <>
          <p className="retail-subtitle">Товары и цены проверены по текущему каталогу.</p>
          <ul className="retail-order-lines">
            {preview.items.map((item) => (
              <li key={item.product.id}>
                <span>
                  {item.product.name}
                  <small>
                    {formatQuantity(quantityThousandths(item.quantity), item.product.unit)}
                  </small>
                </span>
                <strong>
                  {formatMoney(lineTotal(item.product, quantityThousandths(item.quantity)))}
                </strong>
              </li>
            ))}
          </ul>
          {preview.changed.length > 0 && (
            <p>Обновилась цена: {preview.changed.map((item) => item.name).join(', ')}.</p>
          )}
          {preview.unavailable.length > 0 && (
            <div>
              <h3>Не добавляем</h3>
              {preview.unavailable.map((item, index) => (
                <p key={index}>
                  {item.name}: {item.reason}
                </p>
              ))}
            </div>
          )}
          <button
            className="button button-primary"
            disabled={busy || added || !preview.items.length}
            onClick={() => prepare(true)}
          >
            {busy ? 'Проверяем…' : added ? 'Добавлено' : 'Добавить в текущую корзину'}
          </button>
          {added && (
            <Link className="button button-secondary" to="/cart">
              Перейти в корзину
            </Link>
          )}
        </>
      )}
      <p role="status">{notice}</p>
    </section>
  );
}
