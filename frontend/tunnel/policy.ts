/** Fail-closed policy shared by the public preview and its security tests. */
export function tunnelHostname(value: string | undefined): string | undefined {
  if (!value) return undefined;
  const hostname = value.trim().toLowerCase();
  if (!/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.trycloudflare\.com$/.test(hostname)) {
    throw new Error('MINIAPP_TUNNEL_HOST должен содержать один точный hostname вида example.trycloudflare.com, без URL, порта и wildcard.');
  }
  return hostname;
}

export function allowedRequestHost(header: string | undefined, hostname: string): boolean {
  if (!header || !/^[a-z0-9.-]+(?::[0-9]{1,5})?$/i.test(header)) return false;
  const [host, port] = header.toLowerCase().split(':');
  if (host === hostname) return !port || port === '443';
  return (host === '127.0.0.1' || host === 'localhost') && (!port || port === '5174');
}

export type PublicRoute = 'api' | 'media' | 'page' | 'asset';

export function publicRoute(rawUrl: string, files: ReadonlySet<string>): PublicRoute | undefined {
  if (!rawUrl.startsWith('/') || rawUrl.startsWith('//') || rawUrl.length > 4096 || rawUrl.includes('#')) return undefined;
  const rawPath = rawUrl.split('?')[0];
  if (/%(?:2f|5c|00)/i.test(rawPath)) return undefined;
  let path: string;
  try { path = decodeURIComponent(rawPath); } catch { return undefined; }
  if (/[\u0000-\u001f\u007f\\]/.test(path) || /%[a-f0-9]{2}/i.test(path)) return undefined;
  if (path.split('/').some((part) => part.startsWith('.'))) return undefined;
  if (/^\/api\/(?:products(?:\/[1-9]\d{0,9})?|categories|banners)\/$/.test(path)) {
    return path === rawPath ? 'api' : undefined;
  }
  if (rawPath.startsWith('/media/') && /^\/media\/(?:products\/|content\/(?:banners|categories)\/).+\.(?:png|jpe?g|webp|avif|gif)$/i.test(path)) {
    return path.includes('//') ? undefined : 'media';
  }
  if (path !== rawPath) return undefined;
  if (files.has(path)) return 'asset';
  if (/^\/(?:catalog|ideas|cart|profile)?\/?$/.test(path)) return 'page';
  if (/^\/product\/[1-9]\d{0,9}\/?$/.test(path)) return 'page';
  if (/^\/ideas\/(?:cook|recipes|games|collections)\/?$/.test(path)) return 'page';
  if (/^\/profile\/(?:orders|store|help|about)\/?$/.test(path)) return 'page';
  if (/^\/promotions\/[a-zA-Z0-9_-]{1,100}\/?$/.test(path)) return 'page';
  return undefined;
}

export const publicHeaders = {
  'X-Miniapp-Public-Gateway': '1',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
  'Content-Security-Policy': [
    "default-src 'self'",
    "script-src 'self' https://telegram.org",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'none'",
    'frame-ancestors https://web.telegram.org',
  ].join('; '),
} as const;
