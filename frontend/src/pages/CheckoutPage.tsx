import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ChevronDown, MapPin } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useCart } from '../context/CartContext';
import { useSession } from '../context/SessionContext';
import { useCartValidation } from '../hooks/useCartValidation';
import { createOrder, ApiError } from '../lib/api';
import { finishOrderRequest, orderRequestId } from '../lib/orderRequest';
import { formatMoney, formatQuantity, lineTotal } from '../lib/quantity';
import { BackLink } from '../components/Retail';
import { ErrorState } from '../components/States';
import { formatPhoneInput } from '../lib/phone';

export default function CheckoutPage() {
  const cart = useCart();
  const session = useSession();
  const validation = useCartValidation();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (session.data?.user?.phone)
      setPhone((value) => value || formatPhoneInput(session.data!.user!.phone!));
    if (session.data?.authenticated && session.data.user)
      setName(
        (value) =>
          value ||
          [session.data!.user!.first_name, session.data!.user!.last_name].filter(Boolean).join(' '),
      );
  }, [session.data]);
  const ready =
    !!session.data?.checkout_enabled &&
    session.data.authenticated &&
    !validation.checking &&
    !validation.error &&
    cart.items.length > 0 &&
    cart.items.length <= 100 &&
    cart.items.every((item) => item.product.is_available);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ready || pending.current) return;
    pending.current = true;
    setBusy(true);
    setError('');
    const items = cart.items.map((item) => ({
      product_id: item.product.id,
      quantity: `${Math.floor(item.quantity / 1000)}.${String(item.quantity % 1000).padStart(3, '0')}`,
      expected_price: item.product.price,
    }));
    try {
      const request_id = await orderRequestId({
        user: session.data?.user?.id,
        name: name.trim(),
        phone: phone.trim(),
        comment: comment.trim(),
        items,
      });
      const order = await createOrder({
        fulfillment: 'pickup',
        request_id,
        buyer_name: name.trim(),
        phone: phone.trim(),
        comment: comment.trim(),
        items,
      });
      cart.clear();
      finishOrderRequest();
      session.retry();
      navigate(`/profile/orders/${order.id}`, {
        replace: true,
        state: { created: true },
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось сохранить заявку.');
      if (reason instanceof ApiError && (reason.status === 409 || reason.status === 400))
        validation.retry();
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <>
      <BackLink fallback="/cart" />
      <div className="page-intro">
        <h1>Самовывоз</h1>
        <p>Проверьте покупки и оставьте контакты</p>
      </div>
      {!cart.items.length ? (
        <div className="rp-empty">
          <h2>Добавьте товары в корзину</h2>
          <Link className="button button-primary" to="/catalog">
            Открыть каталог
          </Link>
        </div>
      ) : (
        <form className="retail-checkout-form" onSubmit={submit}>
          <div className="retail-pickup">
            <MapPin size={22} />
            <div>
              <strong>Забрать в магазине</strong>
              <p>{session.data?.store.address || 'Севастополь, Камышовое шоссе, 25'}</p>
              <span>Без доставки и онлайн-оплаты</span>
              <span>Наличие подтвердит сотрудник после получения заявки.</span>
            </div>
          </div>
          <details className="retail-order-composition" open>
            <summary>
              <span>Состав заявки · {cart.itemCount} поз.</span>
              <ChevronDown className="order-chevron" size={19} aria-hidden="true" />
            </summary>
            <ul>
              {cart.items.map(({ product, quantity }) => (
                <li key={product.id}>
                  <span>
                    {product.name}
                    <small>{formatQuantity(quantity, product.unit)}</small>
                  </span>
                  <strong>{formatMoney(lineTotal(product, quantity))}</strong>
                </li>
              ))}
            </ul>
            <div>
              <strong>Итого</strong>
              <strong>{formatMoney(cart.totalKopecks)}</strong>
            </div>
          </details>
          {session.data?.weight_estimate &&
            cart.items.some((item) => item.product.unit === 'kg') && (
              <p className="inline-notice">
                Стоимость весовых товаров и итог уточняются после фактического взвешивания.
              </p>
            )}
          <label>
            Ваше имя
            <input
              name="buyer_name"
              autoComplete="name"
              required
              maxLength={100}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label>
            Номер телефона
            <input
              name="phone"
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              placeholder="+7 900 000-00-00"
              required
              maxLength={32}
              value={phone}
              onChange={(event) => setPhone(formatPhoneInput(event.target.value))}
            />
          </label>
          <label>
            Комментарий <span>Необязательно</span>
            <textarea
              name="comment"
              rows={3}
              maxLength={1000}
              placeholder="Что учесть при сборке"
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
          </label>
          {session.error && <ErrorState compact retry={session.retry} message={session.error} />}
          {!session.loading && !session.error && !session.data?.checkout_enabled && (
            <p className="inline-notice" role="status">
              Приём заявок пока выключен. Выбранные товары останутся в корзине.
            </p>
          )}
          {!session.loading && session.data?.checkout_enabled && !session.data.authenticated && (
            <p className="inline-notice">
              Для отправки заявки откройте магазин в Telegram: так заказ появится в вашей истории.
            </p>
          )}
          {validation.error && (
            <div className="inline-notice">
              Не удалось обновить цены и наличие.
              <button type="button" className="button button-secondary" onClick={validation.retry}>
                Проверить ещё раз
              </button>
            </div>
          )}
          {cart.items.length > 100 && (
            <p className="inline-notice">В одной заявке можно оформить до 100 разных товаров.</p>
          )}
          {error && (
            <p className="inline-notice" role="alert">
              {error}
            </p>
          )}
          <button className="button button-primary" type="submit" disabled={!ready || busy}>
            {busy ? 'Сохраняем заявку…' : 'Подтвердить самовывоз'}
          </button>
          <p className="retail-checkout-note">Контакты будут переданы магазину вместе с заявкой.</p>
        </form>
      )}
    </>
  );
}
