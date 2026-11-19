import { useState, useEffect, useCallback } from 'react';
import { ChevronRight, CircleHelp, MapPin, Phone, ReceiptText, UserRound } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useSession } from '../context/SessionContext';
import { ErrorState } from '../components/States';
import { fetchOrders, updateCustomerPhone } from '../lib/api';
import { useResource } from '../hooks/useResource';
import { formatPhoneInput } from '../lib/phone';
import { formatMoney, priceKopecks } from '../lib/quantity';
import { STORE_BRAND } from '../data/brand';

const rows = [
  {
    to: '/profile/orders',
    title: 'Мои заказы',
    description: 'Заявки на самовывоз и их статусы',
    icon: ReceiptText,
  },
  {
    to: '/about',
    title: 'О нас',
    description: 'Магазин, фотографии и график работы',
    icon: MapPin,
  },
  {
    to: '/about',
    title: 'Контакты',
    description: 'Как связаться с магазином',
    icon: Phone,
  },
  {
    to: '/profile/help',
    title: 'Помощь',
    description: 'О покупках и самовывозе',
    icon: CircleHelp,
  },
];
export default function ProfilePage() {
  const session = useSession();
  const user = session.data?.authenticated ? session.data.user : null;
  const [editing, setEditing] = useState(false);
  const [phone, setPhone] = useState('');
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const [photoFailed, setPhotoFailed] = useState(false);
  useEffect(() => {
    setPhone(formatPhoneInput(user?.phone || ''));
  }, [user?.phone]);
  useEffect(() => {
    setPhotoFailed(false);
  }, [user?.photo_url]);
  const loadOrders = useCallback(
    (signal: AbortSignal) => (user ? fetchOrders(1, signal) : Promise.resolve(null)),
    [user?.id],
  );
  const orders = useResource(loadOrders);
  return (
    <>
      <div className="page-intro">
        <h1>Профиль</h1>
      </div>
      <div className="retail-user-card">
        <span className="customer-avatar-frame">
          {user?.photo_url && !photoFailed ? (
            <img
              className="customer-avatar"
              src={user.photo_url}
              alt=""
              referrerPolicy="no-referrer"
              onError={() => setPhotoFailed(true)}
            />
          ) : (
            <UserRound size={30} strokeWidth={1.5} />
          )}
        </span>
        <div>
          <h2>
            {session.loading
              ? 'Проверяем вход…'
              : user
                ? [user.first_name, user.last_name].filter(Boolean).join(' ')
                : session.error
                  ? 'Вход не подтверждён'
                  : 'Вы в гостях'}
          </h2>
          <p>
            {user
              ? user.username
                ? `@${user.username}`
                : 'Вход подтверждён через Telegram'
              : 'Корзина сохранится на этом устройстве'}
          </p>
        </div>
      </div>
      {session.error && <ErrorState compact retry={session.retry} message={session.error} />}
      {!user && !session.loading && session.data?.telegram_url && (
        <a className="button button-secondary" href={session.data.telegram_url}>
          Открыть магазин в Telegram
        </a>
      )}
      {user && (
        <section className="customer-contact">
          <div>
            <h2>Контактный номер</h2>
            <button
              className="retail-text-link"
              onClick={() => {
                setEditing(!editing);
                setNotice('');
              }}
            >
              {editing ? 'Отмена' : user.phone ? 'Изменить' : 'Добавить'}
            </button>
          </div>
          {!editing && (
            <p>
              {user.phone
                ? formatPhoneInput(user.phone)
                : 'Укажите при оформлении заказа или добавьте сейчас'}
            </p>
          )}
          {editing && (
            <form
              onSubmit={async (event) => {
                event.preventDefault();
                if (saving) return;
                setSaving(true);
                setNotice('');
                try {
                  const saved = await updateCustomerPhone(phone);
                  setPhone(formatPhoneInput(saved.phone));
                  session.retry();
                  setEditing(false);
                  setNotice('Номер сохранён.');
                } catch (reason) {
                  setNotice(
                    reason instanceof Error ? reason.message : 'Не удалось сохранить номер.',
                  );
                } finally {
                  setSaving(false);
                }
              }}
            >
              <label>
                Номер телефона
                <input
                  type="tel"
                  autoComplete="tel"
                  inputMode="tel"
                  maxLength={32}
                  value={phone}
                  onChange={(event) => setPhone(formatPhoneInput(event.target.value))}
                />
              </label>
              <button className="button button-primary" disabled={saving}>
                {saving ? 'Сохраняем…' : 'Сохранить номер'}
              </button>
            </form>
          )}
          <p role="status">{notice}</p>
        </section>
      )}
      {user && (
        <section className="customer-recent">
          <div className="rp-section-heading">
            <h2>Мои заказы</h2>
            <Link to="/profile/orders">
              Все заказы <ChevronRight size={16} />
            </Link>
          </div>
          {orders.error ? (
            <ErrorState compact retry={orders.retry} message={orders.error} />
          ) : orders.loading ? (
            <p role="status">Загружаем заказы…</p>
          ) : !orders.data?.results.length ? (
            <div className="customer-empty-orders">
              <ReceiptText size={26} strokeWidth={1.4} />
              <h3>Здесь появятся заказы</h3>
              <p>После первого заказа здесь появятся его состав и статус.</p>
              <Link className="retail-text-link" to="/catalog">
                Выбрать продукты <ChevronRight size={16} />
              </Link>
            </div>
          ) : (
            <div className="retail-orders">
              {orders.data.results.slice(0, 3).map((order) => (
                <Link key={order.id} to={`/profile/orders/${order.id}`}>
                  <span className="retail-order-status">{order.status_label}</span>
                  <strong>{order.number}</strong>
                  <div>
                    <span>
                      {new Date(order.created_at).toLocaleDateString('ru-RU', {
                        timeZone: 'Europe/Moscow',
                      })}
                    </span>
                    <strong>{formatMoney(priceKopecks({ price: order.total }))}</strong>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </section>
      )}
      <nav className="retail-profile-menu" aria-label="Разделы профиля">
        {rows.map(({ to, title, description, icon: Icon }) => (
          <Link key={title} to={to}>
            <span className="retail-profile-icon">
              <Icon size={23} strokeWidth={1.6} />
            </span>
            <span>
              <strong>{title}</strong>
              <small>{description}</small>
            </span>
            <ChevronRight size={18} strokeWidth={1.5} />
          </Link>
        ))}
      </nav>
      <div className="retail-profile-brand">
        <span>{STORE_BRAND}</span>
        <p>Всегда большой выбор хорошего мяса!</p>
      </div>
    </>
  );
}
