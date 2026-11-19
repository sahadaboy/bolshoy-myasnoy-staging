import {
  MapPin,
  Mail,
  Phone,
  CircleHelp,
  SlidersHorizontal,
  ShieldCheck,
  ReceiptText,
  ChevronDown,
} from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { useSession } from '../context/SessionContext';
import { BackLink } from '../components/Retail';
import { STORE_BRAND } from '../data/brand';

const helpItems = [
  {
    title: 'Как купить продукты?',
    icon: CircleHelp,
    text: 'Выберите товары в каталоге, проверьте количество в корзине и перейдите к оформлению самовывоза. Если приём заявок включён, отправленная заявка появится в ваших заказах.',
  },
  {
    title: 'Где забрать покупки?',
    icon: MapPin,
    text: 'Севастополь, Камышовое шоссе, 25. В приложении нет доставки и онлайн-оплаты.',
  },
  {
    title: 'Как изменить количество?',
    icon: SlidersHorizontal,
    text: 'Используйте плюс и минус в карточке или корзине. Для весовых товаров количество показывается в килограммах, для штучных — в штуках.',
  },
  {
    title: 'Почему не видна история заказов?',
    icon: ShieldCheck,
    text: 'История доступна после подтверждённого входа через Telegram. В обычном браузере вы можете просматривать каталог и сохранять корзину.',
  },
  {
    title: 'Как узнать, готова ли заявка?',
    icon: ReceiptText,
    text: 'Откройте «Мои заказы» и обновите статус нужной заявки. Время готовности в приложении не назначается автоматически.',
  },
];

export default function ProfileInfoPage() {
  const { module } = useParams();
  const { data } = useSession();
  const store = data?.store;
  const title =
    module === 'store'
      ? 'О магазине'
      : module === 'contacts'
        ? 'Контакты'
        : module === 'help'
          ? 'Помощь'
          : module === 'about'
            ? 'О приложении'
            : 'Страница не найдена';
  return (
    <>
      <BackLink fallback="/profile" />
      <div className="page-intro">
        <h1>{title}</h1>
      </div>
      <div className="retail-info">
        {(module === 'store' || module === 'contacts') && (
          <>
            <div className="retail-store-address">
              <MapPin size={26} strokeWidth={1.5} />
              <strong>{STORE_BRAND}</strong>
              <p>{store?.address || 'Севастополь, Камышовое шоссе, 25'}</p>
            </div>
            {module === 'store' && (
              <p>
                Единственная точка самовывоза. Состав заявки и её статус доступны в разделе «Мои
                заказы».
              </p>
            )}
            {module === 'contacts' && (
              <div className="retail-contact-links">
                {store?.phone ? (
                  <a href={`tel:${store.phone}`}>
                    <Phone size={20} />
                    {store.phone}
                  </a>
                ) : (
                  <p>Контактный телефон магазина пока не указан.</p>
                )}
                {store?.email && (
                  <a href={`mailto:${store.email}`}>
                    <Mail size={20} />
                    {store.email}
                  </a>
                )}
              </div>
            )}
          </>
        )}
        {module === 'help' &&
          helpItems.map(({ title, text, icon: Icon }, index) => (
            <details key={title} open={index === 0} className="retail-help-topic">
              <summary>
                <Icon size={20} strokeWidth={1.6} aria-hidden="true" />
                <span>{title}</span>
                <ChevronDown
                  className="help-chevron"
                  size={18}
                  strokeWidth={1.6}
                  aria-hidden="true"
                />
              </summary>
              <p>{text}</p>
            </details>
          ))}
        {module === 'about' && (
          <>
            <span className="rp-logo">
              <img src="/brand-logo-original.png" alt="" width="52" height="52" />
            </span>
            <h2>Большой Мясной</h2>
            <p>Всегда большой выбор хорошего мяса!</p>
            <p>
              Каталог магазина, рецепты для вдохновения и заявки на самовывоз в одном приложении.
            </p>
            <p>Цены и доступность для заявки приходят из каталога магазина.</p>
          </>
        )}
        <Link className="button button-secondary" to="/profile">
          В профиль
        </Link>
      </div>
    </>
  );
}
