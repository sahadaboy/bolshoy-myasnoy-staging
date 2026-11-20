import { useCallback } from 'react';
import { ReceiptText, RefreshCw } from 'lucide-react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { useSession } from '../context/SessionContext';
import { useOrderResource as useResource } from '../hooks/useOrderResource';
import { pickupLabel } from '../lib/pickup';
import '../pickup.css';
import { fetchOrder, fetchOrders } from '../lib/api';
import { formatMoney, formatQuantity, priceKopecks, quantityThousandths } from '../lib/quantity';
import { BackLink } from '../components/Retail';
import { ErrorState, LoadingGrid } from '../components/States';
import { RepeatOrder } from '../components/RepeatOrder';

const date = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  timeZone: 'Europe/Moscow',
});

function GuestOrders() {
  return (
    <div className="rp-empty">
      <ReceiptText size={36} strokeWidth={1.4} />
      <h2>Ваши заказы — в Telegram</h2>
      <p>
        Откройте приложение из Telegram, чтобы увидеть историю своих заявок. Каталог и корзина
        доступны и в браузере.
      </p>
      <Link className="button button-secondary" to="/catalog">
        В каталог
      </Link>
    </div>
  );
}

export function OrdersPage() {
  const sessionState = useSession();
  const session = {
    ...sessionState,
    loading: sessionState.loading && !sessionState.data,
    error: sessionState.data ? null : sessionState.error,
  };
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Math.floor(Number(params.get('page')) || 1));
  const authenticated = !!session.data?.authenticated;
  const load = useCallback(
    (signal: AbortSignal) => (authenticated ? fetchOrders(page, signal) : Promise.resolve(null)),
    [page, authenticated, session.data?.user?.id],
  );
  const resource = useResource(
    load,
    `${session.data?.user?.id}:history:${page}`,
    authenticated,
    (result) =>
      !!result?.results.some((order) => !['collected', 'cancelled'].includes(order.status)),
  );
  return (
    <>
      <BackLink fallback="/profile" />
      <div className="page-intro">
        <h1>Мои заказы</h1>
        <p>Заявки на самовывоз</p>
      </div>
      {session.loading ? (
        <LoadingGrid count={2} />
      ) : session.error ? (
        <ErrorState retry={session.retry} message={session.error} />
      ) : !authenticated ? (
        <GuestOrders />
      ) : resource.loading ? (
        <LoadingGrid count={2} />
      ) : resource.error ? (
        <ErrorState retry={resource.retry} message={resource.error} />
      ) : !resource.data?.results.length ? (
        <div className="rp-empty">
          <ReceiptText size={36} strokeWidth={1.4} />
          <h2>Здесь будут ваши заказы</h2>
          <p>Сохранённые заявки появятся после оформления самовывоза.</p>
          <Link className="button button-primary" to="/catalog">
            За покупками
          </Link>
        </div>
      ) : (
        <>
          <div className="retail-orders">
            {resource.data.results.map((order) => (
              <Link key={order.id} to={`/profile/orders/${order.id}`}>
                <span className="retail-order-status">
                  {order.status === 'new' ? 'Ожидает подтверждения оператора' : order.status_label}
                </span>
                <strong>{order.number}</strong>
                {order.pickup_at && <span>Забрать: {pickupLabel(order.pickup_at)}</span>}
                <span>{date.format(new Date(order.created_at))}</span>
                <div>
                  <span>Позиций: {order.item_count}</span>
                  <strong>{formatMoney(priceKopecks({ price: order.total }))}</strong>
                </div>
              </Link>
            ))}
          </div>
          <div className="retail-pagination">
            {resource.data.previous && (
              <button
                className="button button-secondary"
                onClick={() => setParams({ page: String(page - 1) })}
              >
                Назад
              </button>
            )}
            {resource.data.next && (
              <button
                className="button button-secondary"
                onClick={() => setParams({ page: String(page + 1) })}
              >
                Дальше
              </button>
            )}
          </div>
        </>
      )}
    </>
  );
}

export function OrderPage() {
  const { id = '' } = useParams();
  const sessionState = useSession();
  const session = {
    ...sessionState,
    loading: sessionState.loading && !sessionState.data,
    error: sessionState.data ? null : sessionState.error,
  };
  const location = useLocation();
  const authenticated = !!session.data?.authenticated;
  const load = useCallback(
    (signal: AbortSignal) => (authenticated ? fetchOrder(id, signal) : Promise.resolve(null)),
    [id, authenticated, session.data?.user?.id],
  );
  const resource = useResource(
    load,
    `${session.data?.user?.id}:${id}`,
    authenticated,
    (result) => !!result && !['collected', 'cancelled'].includes(result.status),
  );
  const order = resource.data;
  return (
    <>
      <BackLink fallback="/profile/orders" />
      {session.loading ? (
        <LoadingGrid count={2} />
      ) : session.error ? (
        <ErrorState retry={session.retry} message={session.error} />
      ) : !authenticated ? (
        <GuestOrders />
      ) : resource.loading ? (
        <LoadingGrid count={2} />
      ) : resource.error || !order ? (
        <ErrorState retry={resource.retry} message={resource.error || 'Заявка не найдена.'} />
      ) : (
        <article className="retail-order-detail">
          {location.state?.created && (
            <p className="retail-saved" role="status">
              Заявка сохранена в магазине
            </p>
          )}
          <div className="page-intro">
            <h1>Ваш заказ</h1>
            <p>{order.number}</p>
          </div>
          <div className="retail-order-state">
            <span>
              {order.status === 'new' ? 'Ожидает подтверждения оператора' : order.status_label}
            </span>
            <button onClick={resource.retry} aria-label="Обновить статус заказа">
              <RefreshCw size={18} />
            </button>
          </div>
          {order.status === 'confirmed' && (
            <div className="order-accepted" role="status">
              <strong>✅ Ваш заказ принят!</strong>
              <p>Оператор подтвердил ваш заказ. Мы приступаем к его подготовке</p>
            </div>
          )}
          {resource.refreshError && (
            <p role="status" className="inline-notice">
              Не удалось обновить статус. Повторим проверку при восстановлении соединения.
            </p>
          )}
          <p className="retail-subtitle">{date.format(new Date(order.created_at))}</p>
          <section>
            <h2>Самовывоз</h2>
            <p>{order.pickup_address}</p>
            {order.pickup_at && <p>Желаемое время: {pickupLabel(order.pickup_at)}</p>}
          </section>
          <section>
            <h2>Состав заказа</h2>
            <ul className="retail-order-lines">
              {order.items.map((item, index) => (
                <li key={index}>
                  <div>
                    {item.product_id ? (
                      <Link to={`/product/${item.product_id}`}>{item.product_name}</Link>
                    ) : (
                      <span>{item.product_name}</span>
                    )}
                    <small>
                      {formatQuantity(quantityThousandths(item.quantity), item.unit)} ×{' '}
                      {formatMoney(priceKopecks({ price: item.unit_price }))}/
                      {item.unit === 'kg' ? 'кг' : 'шт'}
                    </small>
                  </div>
                  <strong>{formatMoney(priceKopecks({ price: item.subtotal }))}</strong>
                </li>
              ))}
            </ul>
            <div className="retail-order-total">
              <strong>Итого</strong>
              <strong>{formatMoney(priceKopecks({ price: order.total }))}</strong>
            </div>
            {order.weight_estimate && (
              <p className="inline-notice">Итоговая стоимость уточняется по фактическому весу.</p>
            )}
          </section>
          <section>
            <h2>Ваши контакты</h2>
            <p>{order.buyer_name}</p>
            <p>{order.phone}</p>
            {order.comment && <p className="retail-order-comment">{order.comment}</p>}
          </section>
          <Link className="button button-secondary" to="/profile/orders">
            Все мои заказы
          </Link>
          <RepeatOrder id={order.id} />
        </article>
      )}
    </>
  );
}
