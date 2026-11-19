import { useRef } from 'react';
import { ArrowRight, MapPin, ShoppingBasket, Trash2, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useCart } from '../context/CartContext';
import { useCartValidation } from '../hooks/useCartValidation';
import { formatMoney, lineTotal, priceKopecks } from '../lib/quantity';
import { ProductImage } from '../components/ProductImage';
import { QuantityControl } from '../components/QuantityControl';
import { Sheet } from '../components/Retail';

export function CartPage() {
  const cart = useCart();
  const validation = useCartValidation();
  const clear = useRef<HTMLDialogElement>(null);
  const unavailable = cart.items.some((item) => !item.product.is_available);
  return !cart.items.length ? (
    <div className="retail-empty-cart">
      <span>
        <ShoppingBasket size={48} strokeWidth={1.3} />
      </span>
      <h1>В корзине пока пусто</h1>
      <p>
        Выберите продукты для большого ужина.
        <br />
        Мы сохраним их до вашего возвращения.
      </p>
      <Link className="button button-primary" to="/catalog">
        За покупками <ArrowRight size={18} />
      </Link>
    </div>
  ) : (
    <>
      <div className="page-heading retail-cart-heading">
        <div>
          <h1>Корзина</h1>
          <p className="retail-subtitle">Позиций: {cart.itemCount}</p>
        </div>
        <button className="retail-clear" onClick={() => clear.current?.showModal()}>
          <Trash2 size={17} />
          Очистить
        </button>
      </div>
      {cart.storageIssue && (
        <p role="status" className="inline-notice">
          Не удалось сохранить корзину на устройстве. Она доступна, пока открыто приложение.
        </p>
      )}
      <section className="retail-cart-items" aria-label="Товары в корзине">
        {cart.items.map(({ product, quantity }) => (
          <article className="retail-cart-item" key={product.id}>
            <Link
              to={`/product/${product.id}`}
              className="retail-cart-photo"
              aria-label={product.name}
            >
              <ProductImage product={product} />
            </Link>
            <div className="retail-cart-copy">
              <Link to={`/product/${product.id}`}>{product.name}</Link>
              <span>
                {formatMoney(priceKopecks(product))} / {product.unit === 'kg' ? 'кг' : 'шт'}
              </span>
              {!product.is_available && (
                <span className="retail-unavailable">Нет в наличии · не входит в итог</span>
              )}
              <div className="retail-cart-controls">
                <QuantityControl
                  product={product}
                  quantity={quantity}
                  onDecrease={() => cart.decrease(product)}
                  onIncrease={() => cart.increase(product)}
                  disabled={!product.is_available}
                />
                <strong>
                  {product.is_available ? formatMoney(lineTotal(product, quantity)) : '—'}
                </strong>
              </div>
            </div>
            <button
              className="retail-remove"
              aria-label={`Удалить ${product.name}`}
              onClick={() => cart.remove(product.id)}
            >
              <X size={18} />
            </button>
          </article>
        ))}
      </section>
      <Link className="retail-continue" to="/catalog">
        Добавить ещё продукты <ArrowRight size={17} />
      </Link>
      <section className="retail-cart-summary">
        <h2>Ваши покупки</h2>
        <div>
          <span>Стоимость товаров</span>
          <span>{formatMoney(cart.totalKopecks)}</span>
        </div>
        <div className="retail-cart-total">
          <strong>Итого</strong>
          <strong>{formatMoney(cart.totalKopecks)}</strong>
        </div>
        <p>
          <MapPin size={17} />
          Самовывоз: Камышовое шоссе, 25
        </p>
      </section>
      {validation.error && (
        <div className="inline-notice" role="alert">
          Не удалось проверить актуальные цены и наличие.
          <button className="button button-secondary" onClick={validation.retry}>
            Проверить ещё раз
          </button>
        </div>
      )}
      {unavailable && (
        <p className="inline-notice">Удалите недоступные товары, чтобы продолжить.</p>
      )}
      {validation.checking || validation.error || unavailable ? (
        <button className="button button-primary retail-checkout" disabled>
          {validation.checking ? 'Проверяем товары…' : 'Проверьте корзину'}
        </button>
      ) : (
        <Link className="button button-primary retail-checkout" to="/checkout">
          Оформить самовывоз <ArrowRight size={18} />
        </Link>
      )}
      <p className="retail-checkout-note">Без онлайн-оплаты. Адрес самовывоза один.</p>
      <Sheet reference={clear} title="Очистить корзину?">
        <p>Все товары будут удалены из корзины.</p>
        <div className="retail-dialog-actions">
          <button className="button button-secondary" onClick={() => clear.current?.close()}>
            Оставить
          </button>
          <button
            className="button button-primary"
            onClick={() => {
              clear.current?.close();
              cart.clear();
            }}
          >
            Очистить
          </button>
        </div>
      </Sheet>
    </>
  );
}
