export interface Category {
  id: number;
  name: string;
  image?: string | null;
  parent_id?: number | null;
}

/** Editorial images managed by the store; no locally invented promotions. */
export interface Banner {
  id: number;
  image: string;
  alt_text: string;
  target_type: 'product' | 'category' | 'promotion' | 'catalog' | 'ideas';
  target_id: number | null;
  promotion_slug?: string;
  target_url: string;
}

/** The fields returned by shop.serializers.ProductSerializer. */
export interface Product {
  id: number;
  name: string;
  sku: string;
  price: string;
  unit: 'kg' | 'pcs';
  min_quantity: string;
  quantity_step: string;
  description: string;
  image: string | null;
  categories: Category[];
  is_available: boolean;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface CartItem {
  product: Product;
  /** Integer thousandths: 1000 means 1 kg or 1 piece. */
  quantity: number;
}

export interface ProductCollection {
  id: number;
  title: string;
  slug: string;
  description: string;
  products: Product[];
}
export interface Storefront {
  banners: Banner[];
  collections: ProductCollection[];
  dinner_enabled: boolean;
}

export interface ArticleCard {
  id: number;
  slug: string;
  title: string;
  kind: 'recipe' | 'collection';
  image: string | null;
  description: string;
  category: string;
  meals: string[];
  duration_minutes: number | null;
  servings: number | null;
  is_demo: boolean;
  is_topic: boolean;
  is_featured: boolean;
}
export interface Ingredient {
  id: number;
  name: string;
  amount: string;
  product: Product | null;
  cart_quantity: string | null;
}
export interface Article extends ArticleCard {
  body: string;
  ingredients: Ingredient[];
  steps: string[];
  recipes: ArticleCard[];
}
export interface IdeasResponse extends PaginatedResponse<ArticleCard> {
  demo: boolean;
  dinner_enabled: boolean;
  categories: { name: string; slug: string }[];
}

export interface StoreProfile {
  name: string;
  description: string;
  address: string;
  opening_hours: string;
  phone: string;
  telegram_url: string;
  vk_url: string;
  instagram_url: string;
  email: string;
  map_url: string;
  map_embed_url: string;
  photos: { id: number; image: string; caption: string; alt_text: string }[];
}
export type DinnerQuestionKey =
  'pantry' | 'dish' | 'spice' | 'servings' | 'preferences' | 'exclude' | 'time';
export interface DinnerSchema {
  enabled: boolean;
  title: string;
  description: string;
  default_servings: number;
  max_servings: number;
  ingredients: { id: number; name: string }[];
  questions: {
    key: DinnerQuestionKey;
    title: string;
    help_text: string;
    required: boolean;
    options: { id: number; label: string; value: string; is_any: boolean }[];
  }[];
}
export interface DinnerAnswers {
  servings: number;
  pantry: number[];
  exclude: number[];
  answers: Record<string, number[]>;
  recipe_id?: number;
  replacements?: Record<string, number>;
}
export interface DinnerIdea {
  id: number;
  slug: string;
  title: string;
  description: string;
  image: string | null;
  notes: string;
  servings: number;
  duration_minutes: number | null;
  steps: string[];
  total: string;
  owned_count: number;
  ingredients: {
    id: number;
    ingredient_type_id: number;
    name: string;
    amount: string;
    have: boolean;
    optional: boolean;
    replacement_id: number;
    alternatives: { id: number; product: Product }[];
    status: 'owned' | 'buy' | 'optional_unavailable';
  }[];
  shopping: { product: Product; quantity: string; ingredient_ids: number[] }[];
}
export interface DinnerPrepared {
  items: { product: Product; quantity: string }[];
  total: string;
  prices_changed: boolean;
}

export interface Session {
  authenticated: boolean;
  user: {
    id: string;
    first_name: string;
    last_name: string;
    username: string;
    customer_id?: number;
    photo_url?: string | null;
    phone?: string;
    registered_at?: string;
  } | null;
  telegram_url?: string | null;
  checkout_enabled: boolean;
  weight_estimate: boolean;
  store: { address: string; phone: string | null; email: string | null };
}
export interface OrderSummary {
  id: string;
  number: string;
  created_at: string;
  total: string;
  status: string;
  status_label: string;
  item_count: number;
}
export interface Order extends Omit<OrderSummary, 'item_count'> {
  buyer_name: string;
  phone: string;
  comment: string;
  pickup_address: string;
  weight_estimate: boolean;
  items: {
    product_id: number | null;
    product_name: string;
    sku: string;
    quantity: string;
    unit: 'kg' | 'pcs';
    unit_price: string;
    subtotal: string;
  }[];
}
export interface OrderRequest {
  fulfillment?: 'pickup';
  request_id: string;
  buyer_name: string;
  phone: string;
  comment: string;
  items: { product_id: number; quantity: string; expected_price: string }[];
}
