import {
  ArrowLeft,
  BookOpen,
  ChefHat,
  Gamepad2,
  Layers,
  MapPin,
  ReceiptText,
  type LucideIcon,
} from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { ideaModules, profileItems, storeAddress, type IdeaIcon } from '../data/modules';

const ideaIcons: Record<IdeaIcon, LucideIcon> = {
  chef: ChefHat,
  book: BookOpen,
  game: Gamepad2,
  layers: Layers,
};

export function ModulePage() {
  const { pathname } = useLocation();
  const idea = ideaModules.find((module) => module.path === pathname);
  const profile = profileItems.find((item) => item.path === pathname);
  const isPromotion = pathname.startsWith('/promotions/');
  const backPath = idea ? '/ideas' : profile ? '/profile' : '/catalog';
  const backLabel = idea ? 'Все идеи' : profile ? 'Профиль' : 'Каталог';

  return (
    <section className="module-page">
      <Link className="module-back" to={backPath}>
        <ArrowLeft size={20} strokeWidth={1.6} aria-hidden="true" />
        {backLabel}
      </Link>
      {idea ? (
        <UpcomingModule
          title={idea.title}
          description={idea.description}
          icon={ideaIcons[idea.icon]}
        />
      ) : profile?.id === 'store' ? (
        <StoreInformation />
      ) : profile?.id === 'help' ? (
        <HelpInformation />
      ) : profile?.id === 'about' ? (
        <AboutInformation />
      ) : profile?.id === 'orders' ? (
        <UpcomingModule
          title="Мои заказы"
          description="История и статусы заказов появятся после подключения оформления. Сейчас можно выбрать продукты и сохранить корзину."
          icon={ReceiptText}
          status="Оформление пока недоступно"
        />
      ) : isPromotion ? (
        <div className="module-panel">
          <h1>Информация об акции</h1>
          <p className="module-description">Подробности появятся после публикации магазином.</p>
          <Link className="button button-primary" to="/catalog">
            В каталог
          </Link>
        </div>
      ) : (
        <div className="module-panel">
          <h1>Раздел не найден</h1>
          <p className="module-description">Вернитесь в каталог, чтобы продолжить покупки.</p>
          <Link className="button button-primary" to="/catalog">
            В каталог
          </Link>
        </div>
      )}
    </section>
  );
}

function UpcomingModule({
  title,
  description,
  icon: Icon,
  status = 'Раздел в разработке',
}: {
  title: string;
  description: string;
  icon: LucideIcon;
  status?: string;
}) {
  return (
    <div className="module-panel">
      <span className="module-icon" aria-hidden="true">
        <Icon size={36} strokeWidth={1.5} />
      </span>
      <h1>{title}</h1>
      <p className="module-description">{description}</p>
      <p className="module-note">{status}</p>
      <Link className="button button-primary" to="/catalog">
        Перейти в каталог
      </Link>
    </div>
  );
}

function StoreInformation() {
  return (
    <div className="module-panel store-information">
      <span className="module-icon" aria-hidden="true">
        <MapPin size={36} strokeWidth={1.5} />
      </span>
      <h1>Информация о магазине</h1>
      <address className="store-address">
        <span>{storeAddress.city}</span>
        <strong>{storeAddress.street}</strong>
      </address>
      <div className="store-details">
        <h2>Самовывоз</h2>
        <p>Получение заказов планируется по этому адресу. Оформление заказов пока не подключено.</p>
      </div>
      <Link className="button button-primary" to="/catalog">
        Открыть каталог
      </Link>
    </div>
  );
}

function HelpInformation() {
  return (
    <div className="module-panel help-information">
      <h1>Помощь</h1>
      <div className="store-details">
        <h2>Как найти товар</h2>
        <p>Введите название в поиске или выберите категорию в каталоге.</p>
      </div>
      <div className="store-details">
        <h2>Как сохранить корзину</h2>
        <p>
          Корзина сохраняется автоматически в этом браузере. Вы можете закрыть приложение и
          вернуться к выбранным продуктам позже.
        </p>
      </div>
      <div className="store-details">
        <h2>Как оформить заказ</h2>
        <p>
          Оформление пока недоступно. Когда оно появится, здесь будет информация о получении заказа.
        </p>
      </div>
      <div className="store-details">
        <h2>Вопросы о товарах</h2>
        <p>Их можно уточнить в магазине: {storeAddress.full}.</p>
      </div>
      <Link className="button button-primary" to="/catalog">
        Открыть каталог
      </Link>
    </div>
  );
}

function AboutInformation() {
  return (
    <div className="module-panel about-information">
      <h1>О приложении</h1>
      <p className="module-description">Приложение магазина «Большой Мясной» в Севастополе.</p>
      <div className="store-details">
        <h2>Доступно сейчас</h2>
        <p>
          Каталог товаров, поиск по названию, выбор количества и корзина с сохранением в этом
          браузере.
        </p>
      </div>
      <div className="store-details">
        <h2>Дальше</h2>
        <p>Оформление заказов, рецепты и другие разделы будут подключаться постепенно.</p>
      </div>
      <a className="licenses-link" href="/image-credits.txt" target="_blank" rel="noreferrer">
        Источники изображений и лицензии
      </a>
      <Link className="button button-primary" to="/catalog">
        Открыть каталог
      </Link>
    </div>
  );
}

export default ModulePage;
