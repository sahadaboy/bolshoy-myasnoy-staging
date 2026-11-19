import { describe, expect, it } from 'vitest';
import { allowedRequestHost, publicRoute, tunnelHostname } from './policy';

const files = new Set(['/index.html', '/assets/index-123.js', '/assets/index-123.css', '/categories/meat.webp', '/brand-logo-original.png']);

describe('public tunnel boundary', () => {
  it('accepts one precise Quick Tunnel hostname and rejects broad/ambiguous input', () => {
    expect(tunnelHostname('one-two.trycloudflare.com')).toBe('one-two.trycloudflare.com');
    expect(tunnelHostname(undefined)).toBeUndefined();
    for (const host of ['true', '.trycloudflare.com', '*.trycloudflare.com', 'trycloudflare.com', 'https://one.trycloudflare.com', 'one.trycloudflare.com:443', 'one.trycloudflare.com.attacker.test', 'localhost', 'one.trycloudflare.com,two.trycloudflare.com']) expect(() => tunnelHostname(host)).toThrow();
  });

  it('rejects unexpected Host headers even if another Vite env setting allows them', () => {
    expect(allowedRequestHost('one.trycloudflare.com', 'one.trycloudflare.com')).toBe(true);
    expect(allowedRequestHost('localhost:5174', 'one.trycloudflare.com')).toBe(true);
    expect(allowedRequestHost('127.0.0.1:5174', 'one.trycloudflare.com')).toBe(true);
    for (const host of [undefined, 'other.trycloudflare.com', 'one.trycloudflare.com.attacker.test', 'one.trycloudflare.com:8000', 'localhost:8002', 'one.trycloudflare.com@attacker.test', 'one.trycloudflare.com/']) expect(allowedRequestHost(host, 'one.trycloudflare.com')).toBe(false);
  });

  it('allows only app routes, intended GET APIs and named build artifacts', () => {
    for (const path of ['/', '/catalog', '/ideas/cook', '/ideas/recipes', '/profile/store', '/cart', '/product/4', '/promotions/weekend']) expect(publicRoute(path, files)).toBe('page');
    for (const path of ['/api/products/', '/api/products/4/', '/api/products/?category=2&page=2&search=%D1%81%D1%8B%D1%80', '/api/categories/', '/api/banners/']) expect(publicRoute(path, files)).toBe('api');
    expect(publicRoute('/assets/index-123.js', files)).toBe('asset');
    expect(publicRoute('/media/products/Logo12025%D0%BA%D0%B0.png', files)).toBe('media');
    expect(publicRoute('/media/content/banners/photo.webp', files)).toBe('media');
  });

  it('fails closed for secrets, raw Vite source, admin, service endpoints and traversal', () => {
    for (const path of ['/admin/', '/api/', '/api/orders/', '/api/auth/', '/health', '/debug/', '/db.sqlite3', '/content.sqlite3', '/config/settings.py', '/.env', '/.git/config', '/src/main.tsx', '/node_modules/vite/package.json', '/@vite/client', '/@fs/C:/Users/test/.env', '/assets/index-123.js.map', '/categories/sources.json', '/README.md', '/media/content.sqlite3', '/media/products/secret.py', '/media/content/banners/.env.png', '/assets/../config/settings.py', '/media/products/%2e%2e/settings.py', '/media/products/%252e%252e/x.png', '/media/products/a%2fb.png', '/%61pi/products/', '/catalog%00', '/catalog#fragment', '//attacker.test', '/%zz']) expect(publicRoute(path, files), path).toBeUndefined();
  });
});
