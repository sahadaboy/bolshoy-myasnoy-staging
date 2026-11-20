import { useCallback } from 'react';
import { CircleCheck } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { useSession } from '../context/SessionContext';
import { useOrderResource } from '../hooks/useOrderResource';
import { fetchOrder } from '../lib/api';
import { pickupLabel } from '../lib/pickup';
import { ErrorState, LoadingGrid } from '../components/States';

export default function OrderSuccessPage() {
  const { id = '' } = useParams();
  const session = useSession();
  const user = session.data?.user?.id;
  const load = useCallback(
    (signal: AbortSignal) =>
      session.data?.authenticated ? fetchOrder(id, signal) : Promise.resolve(null),
    [id, user, session.data?.authenticated],
  );
  const resource = useOrderResource(
    load,
    `${user}:${id}`,
    !!user,
    (result) => !!result && !['collected', 'cancelled'].includes(result.status),
  );
  const order = resource.data;
  if (resource.loading || (session.loading && !session.data)) return <LoadingGrid count={2} />;
  if (!order)
    return (
      <ErrorState
        retry={resource.retry}
        message={resource.error || 'Войдите через Telegram, чтобы открыть свой заказ.'}
      />
    );
  return (
    <section className="order-success">
      <CircleCheck size={42} strokeWidth={1.5} aria-hidden="true" />
      <h1>Спасибо за заказ!</h1>
      <p>
        {order.status === 'new'
          ? 'Ваш заказ успешно оформлен. Ожидайте подтверждения от оператора'
          : order.status === 'confirmed'
            ? 'Оператор подтвердил ваш заказ. Мы приступаем к его подготовке'
            : order.status_label}
      </p>
      <dl>
        <dt>Номер заказа</dt>
        <dd>{order.number}</dd>
        <dt>Желаемая дата и время получения</dt>
        <dd>{pickupLabel(order.pickup_at)}</dd>
        <dt>Статус</dt>
        <dd>
          {order.status === 'new'
            ? 'Ожидает подтверждения'
            : order.status === 'confirmed'
              ? 'Ваш заказ принят!'
              : order.status_label}
        </dd>
      </dl>
      <Link className="button button-primary" to={`/profile/orders/${id}`}>
        Посмотреть заказ
      </Link>
    </section>
  );
}
