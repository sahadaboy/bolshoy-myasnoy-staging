export type IdeaIcon = 'chef' | 'book' | 'game' | 'layers';

export interface IdeaModule {
  id: string;
  path: string;
  title: string;
  summary: string;
  description: string;
  icon: IdeaIcon;
}

/** New modules can be added here without changing the Ideas page layout. */
export const ideaModules: readonly IdeaModule[] = [
  {
    id: 'cook',
    path: '/ideas/cook',
    title: 'Что приготовить?',
    summary: 'По вашим предпочтениям, времени и количеству порций',
    description:
      'Здесь появится подбор блюд по вашим предпочтениям. Можно будет указать время на готовку и количество порций.',
    icon: 'chef',
  },
  {
    id: 'recipes',
    path: '/ideas/recipes',
    title: 'Рецепты',
    summary: 'Завтраки, обеды и ужины с продуктами из магазина',
    description:
      'Здесь появятся рецепты с пошаговым приготовлением и ингредиентами из ассортимента магазина.',
    icon: 'book',
  },
  {
    id: 'games',
    path: '/ideas/games',
    title: 'Мини-игры',
    summary: 'Игры и специальные активности магазина',
    description:
      'Здесь появятся мини-игры и специальные активности. Раздел пока находится в разработке.',
    icon: 'game',
  },
  {
    id: 'collections',
    path: '/ideas/collections',
    title: 'Подборки',
    summary: 'Тематические наборы продуктов для разных случаев',
    description:
      'Здесь появятся тематические подборки продуктов. Состав и цены будут доступны после публикации магазином.',
    icon: 'layers',
  },
];

export type ProfileIcon = 'orders' | 'store' | 'help' | 'about';

export interface ProfileItem {
  id: ProfileIcon;
  path: string;
  title: string;
  summary: string;
}

export const profileItems: readonly ProfileItem[] = [
  {
    id: 'orders',
    path: '/profile/orders',
    title: 'Мои заказы',
    summary: 'История и статусы заказов',
  },
  {
    id: 'store',
    path: '/profile/store',
    title: 'Информация о магазине',
    summary: 'Адрес и самовывоз',
  },
  {
    id: 'help',
    path: '/profile/help',
    title: 'Помощь',
    summary: 'Вопросы о приложении и покупках',
  },
  {
    id: 'about',
    path: '/profile/about',
    title: 'О приложении',
    summary: 'Что доступно сейчас',
  },
];

export const storeAddress = {
  city: 'Севастополь',
  street: 'Камышовое шоссе, 25',
  full: 'Севастополь, Камышовое шоссе, 25',
} as const;
