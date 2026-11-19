import type { Banner } from '../types';
import { primaryCategories } from '../data/primaryCategories';

export interface PreviewProduct {
  id: number;
  name: string;
  price: number;
  unit: 'kg' | 'pcs';
  step: number;
  minimum?: number;
  image: string | null;
  department: string;
  size?: string;
  featured?: boolean;
}

// Read-only catalogue snapshot, 14 November 2026. Prices and units are copied
// from these exact product IDs, not invented. Photos are preview-only examples
// of the corresponding brand, variant and pack size; no SKU binding is changed.
export const previewProducts: PreviewProduct[] = [
  {
    id: 167,
    name: 'Аджика Махеевъ «Острая»',
    size: '190 г',
    price: 120.99,
    unit: 'pcs',
    step: 1,
    image: '/preview/adjika.webp',
    department: 'sauces',
    featured: true,
  },
  {
    id: 381,
    name: 'Горчица Махеевъ «Зернистая»',
    size: '190 г',
    price: 126.99,
    unit: 'pcs',
    step: 1,
    image: '/preview/mustard.webp',
    department: 'sauces',
    featured: true,
  },
  {
    id: 166,
    name: 'Аджика Махеевъ «Острая»',
    size: '140 г',
    price: 76.99,
    unit: 'pcs',
    step: 1,
    image: '/preview/adjika-pouch.webp',
    department: 'sauces',
    featured: true,
  },
  {
    id: 380,
    name: 'Горчица Махеевъ «Зернистая»',
    size: '140 г',
    price: 58.99,
    unit: 'pcs',
    step: 1,
    image: '/preview/mustard-pouch.webp',
    department: 'sauces',
    featured: true,
  },
  {
    id: 4822,
    name: 'Кешью жареный',
    price: 1575,
    unit: 'kg',
    step: 0.1,
    minimum: 0.5,
    image: '/preview/cashew.webp',
    department: 'nuts',
    featured: true,
  },
  // The actual product has no usable photo. Keep its neutral placeholder and
  // its stored pcs unit, even though that unit may need the owner's review.
  {
    id: 1,
    name: 'Говядина мякоть',
    price: 890,
    unit: 'pcs',
    step: 1,
    minimum: 0.5,
    image: null,
    department: 'meat',
  },
];

export const previewDepartments = primaryCategories;
export const previewCategoryList = [
  { id: 'grocery', name: 'Бакалея' },
  { id: 'nonalcoholic', name: 'Безалкогольные напитки' },
  { id: 'water', name: 'Вода' },
  { id: 'dairy', name: 'Молочная продукция' },
  { id: 'seafood', name: 'Морепродукты' },
  { id: 'meat', name: 'Мясо' },
  { id: 'sauces', name: 'Приправы' },
  { id: 'smoked-fish', name: 'Рыба копчёная' },
  { id: 'fish', name: 'Рыба свежемороженая' },
  { id: 'juice', name: 'Соки' },
  { id: 'nuts', name: 'Сухофрукты и орехи' },
  { id: 'cheese', name: 'Сыры' },
];

// Same contract as an Admin banner: a complete image, alternative text, target.
export const previewBanner: Banner = {
  id: -1,
  image: '/preview/dinner-banner.webp',
  alt_text: 'Большой выбор для большого ужина. Всегда большой выбор хорошего мяса!',
  target_type: 'category',
  target_id: 4,
  promotion_slug: '',
  target_url: '/design-preview?department=sauces',
};

export interface Story {
  id: string;
  title: string;
  description: string;
  image: string;
  alt: string;
  meals: string[];
  body: string;
  ingredients: string;
  topic?: boolean;
  recipe?: boolean;
  featured?: boolean;
}

// Demonstration editorial content only. Nothing is published to the real CMS.
export const stories: Story[] = [
  {
    id: 'pasta',
    title: 'Паста и соусы',
    description: 'Простые сочетания на каждый день',
    image: '/preview/pasta.webp',
    alt: 'Паста с песто и пармезаном',
    meals: ['Обед', 'Ужин'],
    topic: true,
    body: 'Отварите пасту до состояния аль денте. Сохраните немного воды от варки, смешайте с песто и пастой. Добавьте тёртый сыр перед подачей.',
    ingredients: 'Паста, песто, твёрдый сыр, свежий базилик.',
  },
  {
    id: 'salads',
    title: 'Салаты к мясу',
    description: 'Овощи, зелень и лёгкие заправки',
    image: '/preview/salad.webp',
    alt: 'Яркий салат с овощами, нутом и авокадо',
    meals: ['Завтрак', 'Обед', 'Ужин'],
    topic: true,
    body: 'Сочетайте хрустящие овощи с салатными листьями. Добавьте нут, авокадо и заправку из оливкового масла с лимонным соком. Смешайте перед подачей.',
    ingredients: 'Салатные листья, помидоры, морковь, нут, авокадо, лимон, оливковое масло.',
  },
  {
    id: 'dinner',
    title: 'Ужин без спешки',
    description: 'Любимые блюда для уютного вечера',
    image: '/preview/carbonara.webp',
    alt: 'Паста на светлом столе с сыром и специями',
    meals: ['Ужин'],
    topic: true,
    body: 'Накройте стол и приготовьте пасту с сыром и беконом. Добавьте свежие овощи и подавайте сразу после приготовления.',
    ingredients: 'Паста, сыр, бекон, свежие овощи.',
  },
  {
    id: 'sunday',
    title: 'Воскресный обед',
    description: 'Курица из духовки, овощи и любимые гарниры',
    image: '/preview/family-dinner.webp',
    alt: 'Запечённая курица с овощами на большом общем блюде',
    meals: ['Обед', 'Ужин'],
    featured: true,
    body: 'Натрите курицу маслом, солью и травами. Запеките до полной готовности, а гарнир приготовьте рядом в отдельной форме. Дайте птице немного отдохнуть перед подачей.',
    ingredients: 'Целая курица, картофель, чеснок, сливки, растительное масло, розмарин, соль.',
  },
  {
    id: 'carbonara',
    title: 'Паста с характером',
    description: 'Сыр, бекон и ничего лишнего',
    image: '/preview/carbonara.webp',
    alt: 'Тарелки пасты с беконом и тёртым сыром',
    meals: ['Обед', 'Ужин'],
    recipe: true,
    body: 'Отварите пасту. Подрумяньте бекон на сковороде, снимите с огня и соедините с пастой. Добавьте смесь желтков и сыра, размешивая и подливая немного воды от варки до кремовой консистенции.',
    ingredients: 'Паста, бекон, яичные желтки, твёрдый сыр, чёрный перец.',
  },
  {
    id: 'green',
    title: 'Больше свежести',
    description: 'Салат с нутом и авокадо',
    image: '/preview/salad.webp',
    alt: 'Салат с зеленью, нутом, овощами и авокадо',
    meals: ['Завтрак', 'Обед', 'Ужин'],
    recipe: true,
    body: 'Нарежьте овощи и авокадо, добавьте готовый нут и зелень. Заправьте оливковым маслом с лимонным соком непосредственно перед подачей.',
    ingredients: 'Нут, авокадо, помидоры, морковь, салатные листья, лимон, оливковое масло.',
  },
];
