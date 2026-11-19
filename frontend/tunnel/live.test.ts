import { describe, it, expect } from 'vitest';
import { liveRoute } from './live';

describe('Live shop boundary', () => {
  it('permits authenticated account/order methods and read-only dinner computation', () => {
    for (const [path, method] of [
      ['/api/session/', 'GET'],
      ['/api/profile/', 'PATCH'],
      ['/api/orders/', 'POST'],
      ['/api/orders/', 'GET'],
      ['/api/orders/12345678-1234-1234-1234-123456789012/repeat/', 'POST'],
      ['/api/dinner/prepare/', 'POST'],
    ])
      expect(liveRoute(path, method, new Set())).toBe('api');
  });
  it('never forwards admin, database, config, debug, encoded traversals or arbitrary writes', () => {
    for (const path of [
      '/admin/',
      '/.env',
      '/db.sqlite3',
      '/@fs/C:/secrets',
      '/api/../admin/',
      '/api/%2e%2e/admin/',
      '/media/products/%252e%252e/db.sqlite3',
      '/api/products/1/',
    ])
      expect(liveRoute(path, 'POST', new Set())).toBeUndefined();
    expect(liveRoute('/admin/', 'GET', new Set())).toBeUndefined();
    expect(liveRoute('/api/profile/', 'GET', new Set())).toBeUndefined();
    expect(liveRoute('/media/products/a.svg', 'GET', new Set())).toBeUndefined();
  });
  it('serves only published assets, known pages and allowed image directories', () => {
    expect(liveRoute('/about/map', 'GET', new Set())).toBe('file');
    expect(liveRoute('/assets/app.js', 'GET', new Set(['/assets/app.js']))).toBe('file');
    expect(liveRoute('/assets/source.ts', 'GET', new Set())).toBeUndefined();
    expect(liveRoute('/media/storefront_uploads/store/photo.webp', 'GET', new Set())).toBe('media');
  });
});
