import type {
  Article,
  Banner,
  Category,
  IdeasResponse,
  Order,
  OrderRequest,
  OrderSummary,
  PaginatedResponse,
  Product,
  Session,
  Storefront,
  StoreProfile,
  DinnerSchema,
  DinnerAnswers,
  DinnerIdea,
  DinnerPrepared,
} from '../types';
import { loadTelegramWebApp } from './telegram';

export interface ProductPage {
  count: number;
  next: string | null;
  previous: string | null;
  results: Product[];
}

export interface ProductFilters {
  category?: string | number;
  categoryGroup?: string;
  search?: string;
  page?: number;
  unit?: string;
  available?: boolean;
  ordering?: string;
  collection?: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly payload?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

const PAGINATION_HELP = 'Каталог временно недоступен. Не удалось получить страницу товаров.';
const MAX_RESPONSE_BYTES = 512 * 1024;

export async function get<T>(
  path: string,
  signal?: AbortSignal,
  requirePage = false,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      signal,
      credentials: 'omit',
      headers: {
        Accept: 'application/json',
        ...privateHeaders(path),
        ...init?.headers,
      },
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError(
      'Не удалось связаться с магазином. Проверьте соединение и попробуйте ещё раз.',
    );
  }
  if (!response.ok && !init) {
    throw new ApiError(
      response.status === 404
        ? path.startsWith('/api/products/')
          ? 'Товар не найден или больше не доступен в каталоге.'
          : 'Страница не найдена или недоступна.'
        : response.status === 401
          ? 'Вход через Telegram не подтверждён. Откройте приложение заново.'
          : 'Не удалось загрузить данные. Попробуйте ещё раз.',
      response.status,
    );
  }
  const reader = response.body?.getReader();
  if (!reader) throw new ApiError('Браузер не поддерживает потоковую загрузку каталога.');
  const decoder = new TextDecoder();
  let json = '';
  let bytes = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      json += decoder.decode(value, { stream: true });
      // An unpaginated backend returns an array. Cancel on its first chunk so
      // the browser never downloads the complete 5,000+ product catalogue.
      if (requirePage && json.trimStart().startsWith('[')) {
        await reader.cancel();
        throw new ApiError(PAGINATION_HELP);
      }
      if (bytes > MAX_RESPONSE_BYTES) {
        await reader.cancel();
        throw new ApiError('Ответ каталога слишком большой. ' + PAGINATION_HELP);
      }
    }
    json += decoder.decode();
    const payload = JSON.parse(json);
    if (!response.ok) {
      const messages =
        typeof payload === 'object' && payload
          ? Object.values(payload)
              .flat()
              .filter((item) => typeof item === 'string')
          : [];
      throw new ApiError(
        response.status === 401
          ? 'Вход через Telegram не подтверждён или устарел. Закройте магазин и откройте его из меню бота.'
          : messages.slice(0, 3).join(' ') ||
              (path.startsWith('/api/profile/')
                ? `Не удалось сохранить номер (HTTP ${response.status}). Повторите попытку.`
                : 'Не удалось выполнить запрос. Проверьте данные и попробуйте ещё раз.'),
        response.status,
        payload,
      );
    }
    return payload as T;
  } catch (error) {
    if (error instanceof ApiError || signal?.aborted) throw error;
    if (!response.ok)
      throw new ApiError(
        response.status === 401
          ? 'Вход через Telegram не подтверждён. Закройте магазин и откройте его из меню бота.'
          : `Сервер не выполнил запрос (HTTP ${response.status}). Повторите попытку.`,
        response.status,
      );
    throw new ApiError('Не удалось прочитать данные магазина. Попробуйте ещё раз.');
  } finally {
    reader.releaseLock();
  }
}

/** DRF returns absolute next URLs. Always keep subsequent requests on our proxy. */
export function localApiPath(url: string, expectedPath = '/api/products/'): string {
  const parsed = new URL(url, window.location.origin);
  if (parsed.pathname !== expectedPath)
    throw new ApiError('Некорректная ссылка следующей страницы.');
  return `${parsed.pathname}${parsed.search}`;
}

export async function fetchCategories(signal?: AbortSignal): Promise<Category[]> {
  const categories: Category[] = [];
  let next: string | null = '/api/categories/';
  const seen = new Set<string>();
  while (next) {
    if (seen.has(next)) throw new ApiError('Сервер повторяет страницу категорий.');
    seen.add(next);
    const response: Category[] | { results: Category[]; next: string | null } = await get(
      next,
      signal,
    );
    if (Array.isArray(response)) {
      categories.push(...response);
      break;
    }
    categories.push(...response.results);
    next = response.next ? localApiPath(response.next, '/api/categories/') : null;
  }
  return [...new Map(categories.map((category) => [category.id, category])).values()];
}

export async function fetchProducts(
  filters: ProductFilters = {},
  signal?: AbortSignal,
): Promise<ProductPage> {
  const params = new URLSearchParams();
  if (filters.category) params.set('category', String(filters.category));
  if (filters.categoryGroup) params.set('category_group', filters.categoryGroup);
  if (filters.search?.trim()) params.set('search', filters.search.trim());
  if (filters.page && filters.page > 1) params.set('page', String(filters.page));
  if (filters.unit) params.set('unit', filters.unit);
  if (filters.available) params.set('available', '1');
  if (filters.ordering) params.set('ordering', filters.ordering);
  if (filters.collection) params.set('collection', filters.collection);
  return fetchProductPage(`/api/products/${params.size ? `?${params}` : ''}`, signal);
}

export async function fetchProductPage(path: string, signal?: AbortSignal): Promise<ProductPage> {
  const page = await get<ProductPage>(localApiPath(path), signal, true);
  if (Array.isArray(page) || !Array.isArray(page.results) || !Number.isInteger(page.count)) {
    throw new ApiError(PAGINATION_HELP);
  }
  return { ...page, next: page.next ? localApiPath(page.next) : null };
}

export function fetchProduct(id: string | number, signal?: AbortSignal): Promise<Product> {
  if (!/^\d+$/.test(String(id))) return Promise.reject(new ApiError('Товар не найден.', 404));
  return get<Product>(`/api/products/${id}/`, signal);
}

export const getProduct = fetchProduct;
export const getCategories = fetchCategories;
export const getProducts = fetchProducts;

export async function fetchBanners(signal?: AbortSignal): Promise<Banner[]> {
  const result = await get<Banner[]>('/api/banners/', signal);
  if (!Array.isArray(result)) throw new ApiError('Не удалось загрузить баннеры.');
  return result.filter(
    (banner) =>
      banner.image && /^\/(product|catalog|promotions|ideas)(\/|\?|$)/.test(banner.target_url),
  );
}

/** Use only the image supplied by the API; local Django images go via Vite. */
export function productImageUrl(image: string | null | undefined): string | null {
  if (!image) return null;
  try {
    const url = new URL(image, window.location.origin);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
    if (url.hostname === 'localhost' || url.hostname === '127.0.0.1')
      return `${url.pathname}${url.search}`;
    return url.href;
  } catch {
    return null;
  }
}

export const fetchStorefront = (signal?: AbortSignal) =>
  get<Storefront>('/api/storefront/', signal);
export const fetchStoreProfile = (signal?: AbortSignal) => get<StoreProfile>('/api/store/', signal);
export const fetchDinnerSchema = (signal?: AbortSignal) =>
  get<DinnerSchema>('/api/dinner/schema/', signal);
export const suggestDinner = (body: DinnerAnswers, signal?: AbortSignal) =>
  get<{ results: DinnerIdea[] }>('/api/dinner/suggestions/', signal, false, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
export const prepareDinner = (
  body: DinnerAnswers & {
    recipe_id: number;
    items: {
      product_id: number;
      quantity: string;
      expected_price: string;
    }[];
  },
  signal?: AbortSignal,
) =>
  get<DinnerPrepared>('/api/dinner/prepare/', signal, false, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
export const fetchIdeas = (params: URLSearchParams, signal?: AbortSignal) =>
  get<IdeasResponse>(`/api/ideas/${params.size ? `?${params}` : ''}`, signal);
export const fetchArticle = (slug: string, signal?: AbortSignal) =>
  get<Article>(`/api/ideas/${encodeURIComponent(slug)}/`, signal);
export const fetchSession = async (signal?: AbortSignal) => {
  await loadTelegramWebApp();
  return get<Session>('/api/session/', signal);
};
export async function updateCustomerPhone(phone: string) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 30000);
  try {
    const result = await get<{ phone: string }>('/api/profile/', controller.signal, false, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone }),
    });
    if (typeof result.phone !== 'string')
      throw new ApiError('Сервер не подтвердил сохранение номера. Обновите профиль.');
    return result;
  } catch (error) {
    if (controller.signal.aborted)
      throw new ApiError(
        'Ответ о сохранении номера задержался. Обновите профиль перед повторной попыткой.',
      );
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}
export interface RepeatPreview {
  items: { product: Product; quantity: string }[];
  unavailable: { name: string; reason: string }[];
  changed: { name: string; before: string; after: string }[];
}
export const repeatOrder = (id: string) =>
  get<RepeatPreview>(`/api/orders/${encodeURIComponent(id)}/repeat/`, undefined, false, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  });
export const fetchOrders = (page = 1, signal?: AbortSignal) =>
  get<PaginatedResponse<OrderSummary>>(`/api/orders/?page=${page}`, signal);
export const fetchOrder = (id: string, signal?: AbortSignal) =>
  get<Order>(`/api/orders/${encodeURIComponent(id)}/`, signal);

function privateHeaders(path: string): Record<string, string> {
  if (!/^\/api\/(session|orders|profile)(\/|$)/.test(path)) return {};
  const raw = window.Telegram?.WebApp?.initData;
  return typeof raw === 'string' && raw ? { Authorization: `tma ${raw}` } : {};
}

/** Orders use a bounded response, a timeout, and the same signed Telegram data. */
export async function createOrder(body: OrderRequest): Promise<Order> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 30_000);
  try {
    const response = await fetch('/api/orders/', {
      method: 'POST',
      credentials: 'omit',
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        ...privateHeaders('/api/orders/'),
      },
      body: JSON.stringify(body),
    });
    const reader = response.body?.getReader();
    if (!reader) throw new ApiError('Не удалось прочитать ответ магазина.');
    const decoder = new TextDecoder();
    let json = '';
    let size = 0;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > MAX_RESPONSE_BYTES) {
          await reader.cancel();
          throw new ApiError('Ответ магазина слишком большой.');
        }
        json += decoder.decode(value, { stream: true });
      }
      json += decoder.decode();
    } finally {
      reader.releaseLock();
    }
    let result: unknown;
    try {
      result = JSON.parse(json);
    } catch {
      throw new ApiError(
        'Не удалось подтвердить сохранение заявки. Проверьте историю или повторите отправку.',
      );
    }
    if (!response.ok) {
      const values =
        typeof result === 'object' && result
          ? Object.values(result)
              .flat()
              .filter((value) => typeof value === 'string')
          : [];
      throw new ApiError(
        values.join(' ').slice(0, 500) ||
          'Не удалось сохранить заявку. Проверьте данные и попробуйте ещё раз.',
        response.status,
        result,
      );
    }
    const order = result as Order;
    if (!order.id || !order.number || !Array.isArray(order.items))
      throw new ApiError('Сервер не подтвердил сохранение заявки. Проверьте историю заказов.');
    return order;
  } catch (reason) {
    if (reason instanceof ApiError) throw reason;
    throw new ApiError(
      'Не удалось получить подтверждение от магазина. Проверьте историю или повторите отправку: повторная заявка не создастся.',
    );
  } finally {
    window.clearTimeout(timeout);
  }
}
