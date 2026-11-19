import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchCategories, fetchProduct, fetchProducts, localApiPath, productImageUrl } from './api';

beforeEach(() => {
  vi.stubGlobal('window', { location: { origin: 'http://localhost:5173' } });
});

afterEach(() => vi.unstubAllGlobals());

describe('API boundaries', () => {
  it('keeps DRF next links on the local proxy and rejects unrelated paths', () => {
    expect(localApiPath('http://127.0.0.1:8001/api/products/?category=2&page=2')).toBe(
      '/api/products/?category=2&page=2',
    );
    expect(localApiPath('/api/products/?page=3')).toBe('/api/products/?page=3');
    expect(() => localApiPath('https://example.com/admin/')).toThrow('Некорректная ссылка');
    expect(() => localApiPath('/api/categories/')).toThrow('Некорректная ссылка');
  });

  it('requests only one product page, preserving filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          count: 50,
          next: 'http://127.0.0.1:8001/api/products/?category=2&search=сыр&page=3',
          previous: null,
          results: [],
        }),
      ),
    );
    vi.stubGlobal('fetch', fetchMock);
    const page = await fetchProducts({ category: '2', search: ' сыр ', page: 2 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/products/?category=2&search=%D1%81%D1%8B%D1%80&page=2',
    );
    expect(page.next).toBe('/api/products/?category=2&search=%D1%81%D1%8B%D1%80&page=3');
    expect(page.count).toBe(50);
  });

  it('cancels an unpaginated catalogue on its first chunk', async () => {
    const cancel = vi.fn();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(' [{"id":1}'));
      },
      cancel,
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body)));
    await expect(fetchProducts()).rejects.toThrow('Не удалось получить страницу товаров');
    expect(cancel).toHaveBeenCalledTimes(1);
  });

  it('bounds oversized API responses instead of retaining an entire catalogue', async () => {
    const cancel = vi.fn();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(`{"data":"${'x'.repeat(600_000)}`));
      },
      cancel,
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body)));
    await expect(fetchProducts()).rejects.toThrow('слишком большой');
    expect(cancel).toHaveBeenCalledTimes(1);
  });

  it('supports both category response shapes and deduplicates paginated categories', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            results: [{ id: 2, name: 'Бакалея' }],
            next: 'http://127.0.0.1:8000/api/categories/?page=2',
          }),
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            results: [
              { id: 2, name: 'Бакалея' },
              { id: 5, name: 'Молочная продукция' },
            ],
            next: null,
          }),
        ),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify([{ id: 12, name: 'Сыры' }])));
    vi.stubGlobal('fetch', fetchMock);
    expect(await fetchCategories()).toEqual([
      { id: 2, name: 'Бакалея' },
      { id: 5, name: 'Молочная продукция' },
    ]);
    expect(fetchMock.mock.calls[1][0]).toBe('/api/categories/?page=2');
    expect(await fetchCategories()).toEqual([{ id: 12, name: 'Сыры' }]);
  });

  it('turns connection failures into a readable retry message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(fetchProducts()).rejects.toThrow('Проверьте соединение');
  });

  it('reports missing products and server failures', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(new Response('', { status: 404 }))
        .mockResolvedValueOnce(new Response('', { status: 500 })),
    );
    await expect(fetchProduct(999999)).rejects.toMatchObject({
      status: 404,
      message: expect.stringContaining('не найден'),
    });
    await expect(fetchProducts()).rejects.toMatchObject({
      status: 500,
      message: expect.stringContaining('ещё раз'),
    });
  });

  it('passes cancellation through without disguising it as a server failure', async () => {
    const controller = new AbortController();
    const error = new DOMException('Aborted', 'AbortError');
    controller.abort();
    const fetchMock = vi.fn().mockRejectedValue(error);
    vi.stubGlobal('fetch', fetchMock);
    await expect(fetchProducts({}, controller.signal)).rejects.toBe(error);
    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal);
  });

  it('reports malformed JSON and rejects invalid product identifiers without requesting', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('<html>not JSON</html>'));
    vi.stubGlobal('fetch', fetchMock);
    await expect(fetchCategories()).rejects.toThrow('Не удалось прочитать данные');
    await expect(fetchProduct('../admin')).rejects.toMatchObject({ status: 404 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('uses only API images and safely proxies local media', () => {
    expect(productImageUrl(null)).toBeNull();
    expect(productImageUrl('javascript:alert(1)')).toBeNull();
    expect(productImageUrl('http://127.0.0.1:8001/media/products/photo.png')).toBe(
      '/media/products/photo.png',
    );
    expect(productImageUrl('https://cdn.example.com/photo.png')).toBe(
      'https://cdn.example.com/photo.png',
    );
  });
});
