/** Explicit application gateway. Admin, source files and Django debug HTML stay private. */
import { request as httpRequest, type IncomingMessage, type ServerResponse } from 'node:http';
import { resolve } from 'node:path';
import type { Plugin } from 'vite';
import { publicFiles } from './gateway';

export function liveRoute(
  raw: string,
  method: string,
  files: Set<string>,
): 'api' | 'media' | 'file' | undefined {
  let path: string;
  try {
    path = decodeURIComponent(raw);
  } catch {
    return;
  }
  if (
    /[\u0000-\u001f\u007f\\%]/.test(path) ||
    path.includes('//') ||
    path.split('/').some((part) => part.startsWith('.'))
  )
    return;
  if (/^\/media\/(products|storefront_uploads)\/.+\.(png|jpe?g|webp|avif)$/i.test(path))
    return /^(GET|HEAD)$/.test(method) ? 'media' : undefined;
  if (path !== raw) return;
  const read =
    /^\/api\/(?:products(?:\/[1-9]\d*)?|categories|banners|storefront|store|pickup-slots|session|dinner\/schema|ideas(?:\/[a-z0-9_-]+)?|orders(?:\/[a-f0-9-]{36})?)\/$/.test(
      path,
    );
  const write =
    (method === 'PATCH' && path === '/api/profile/') ||
    (method === 'POST' && ['/api/cart/', '/api/session/login/', '/api/profile/'].includes(path)) ||
    (method === 'POST' &&
      /^\/api\/(?:orders|orders\/[a-f0-9-]{36}\/repeat|dinner\/(suggestions|prepare))\/$/.test(
        path,
      ));
  if (((read || path === '/api/cart/') && method === 'GET') || write) return 'api';
  if (!/^(GET|HEAD)$/.test(method)) return;
  if (files.has(path) || /^\/brand\/(telegram|vk)\.svg$/.test(path)) return 'file';
  if (
    /^\/(?:catalog|about(?:\/map)?|ideas(?:\/dinner|\/article\/[a-z0-9_-]+|\/recipes|\/collections)?|cart|checkout|profile(?:\/orders(?:\/[a-f0-9-]{36}(?:\/success)?)?|\/store|\/about|\/contacts|\/help)?|product\/[1-9]\d*)?\/?$/.test(
      path,
    )
  )
    return 'file';
}

function fail(res: ServerResponse, status: number) {
  if (res.writableEnded) return;
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.end(
    JSON.stringify({ detail: status === 404 ? 'Not found.' : 'Сервис временно недоступен.' }),
  );
}

export function liveGateway(hostname: string, target: string): Plugin {
  if (!/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])$/.test(hostname) || !hostname.includes('.'))
    throw new Error('Укажите точный hostname Mini App.');
  const backend = new URL(target);
  if (backend.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(backend.hostname))
    throw new Error('Backend должен слушать loopback.');
  return {
    name: 'miniapp-live-gateway',
    configureServer() {
      throw new Error('Режим live использует pnpm build и vite preview, без dev-сервера.');
    },
    configurePreviewServer(server) {
      const files = publicFiles(resolve(server.config.root, server.config.build.outDir));
      server.middlewares.use((req: IncomingMessage, res: ServerResponse, next: () => void) => {
        res.setHeader('Cache-Control', 'private, no-store');
        res.setHeader('X-Content-Type-Options', 'nosniff');
        res.setHeader('Referrer-Policy', 'no-referrer');
        res.setHeader('X-Miniapp-Live-Gateway', '1');
        res.setHeader(
          'Content-Security-Policy',
          "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self'; frame-src https://yandex.ru https://yandex.com; object-src 'none'; base-uri 'self'; frame-ancestors https://web.telegram.org https://*.telegram.org",
        );
        const host = req.headers.host || '';
        const address = server.httpServer.address();
        const port =
          address && typeof address !== 'string' ? address.port : server.config.preview.port;
        if (![hostname, `127.0.0.1:${port}`, `localhost:${port}`].includes(host))
          return fail(res, 403);
        if (
          req.headers.origin &&
          ![`https://${hostname}`, `http://${host}`].includes(req.headers.origin)
        )
          return fail(res, 403);
        const rawPath = (req.url || '').split('?')[0];
        const route = liveRoute(rawPath, req.method || '', files);
        if (!route) return fail(res, 404);
        if (route === 'file') {
          next();
          return;
        }
        const parts: Buffer[] = [];
        let bytes = 0;
        req.on('data', (part: Buffer) => {
          bytes += part.length;
          if (bytes > 65536) {
            fail(res, 413);
          } else parts.push(part);
        });
        req.on('end', () => {
          if (res.writableEnded) return;
          const body = Buffer.concat(parts);
          const headers: Record<string, string> = {
            Accept: route === 'api' ? 'application/json' : 'image/*',
            'Accept-Encoding': 'identity',
            // Trusted only when Django's explicit DJANGO_TRUST_PROXY flag is on.
            // Never copy a client-supplied forwarding header.
            'X-Forwarded-Proto': host === hostname ? 'https' : 'http',
          };
          if (body.length) {
            headers['Content-Type'] = 'application/json';
            headers['Content-Length'] = String(body.length);
          }
          const authorization = req.headers.authorization;
          headers.Host = host;
          if (req.headers.origin) headers.Origin = req.headers.origin;
          const customerCookies = req.headers.cookie
            ?.split(';')
            .map((value) => value.trim())
            .filter((value) => /^(bm_customer|csrftoken)=/.test(value));
          if (customerCookies?.length) headers.Cookie = customerCookies.join('; ');
          if (typeof req.headers['x-csrftoken'] === 'string')
            headers['X-CSRFToken'] = req.headers['x-csrftoken'];
          if (authorization) {
            if (!/^tma /i.test(authorization) || authorization.length > 17000)
              return fail(res, 401);
            headers.Authorization = authorization;
          }
          const proxy = httpRequest(
            new URL(req.url!, backend),
            { method: req.method, headers, timeout: 20000 },
            (upstream) => {
              const type = String(upstream.headers['content-type'] || '').split(';')[0];
              if (
                (upstream.statusCode || 500) >= 500 ||
                upstream.statusCode! < 200 ||
                (upstream.statusCode! >= 300 && upstream.statusCode! < 400) ||
                (route === 'api'
                  ? type !== 'application/json'
                  : !/^image\/(png|jpeg|webp|avif)$/.test(type))
              ) {
                upstream.resume();
                fail(res, 502);
                return;
              }
              const chunks: Buffer[] = [];
              let length = 0;
              upstream.on('data', (chunk: Buffer) => {
                length += chunk.length;
                if (length > (route === 'api' ? 512 * 1024 : 16 * 1024 * 1024)) {
                  upstream.destroy();
                  fail(res, 502);
                } else chunks.push(chunk);
              });
              upstream.on('error', () => fail(res, 502));
              upstream.on('end', () => {
                if (res.writableEnded) return;
                const output = Buffer.concat(chunks);
                if (route === 'api') {
                  try {
                    JSON.parse(output.toString('utf8'));
                  } catch {
                    return fail(res, 502);
                  }
                }
                res.statusCode = upstream.statusCode!;
                res.setHeader('Content-Type', type);
                const customerSetCookies = upstream.headers['set-cookie']?.filter((value) =>
                  /^(bm_customer|csrftoken)=/.test(value),
                );
                if (customerSetCookies?.length) res.setHeader('Set-Cookie', customerSetCookies);
                if (upstream.statusCode === 401) res.setHeader('WWW-Authenticate', 'tma');
                res.end(req.method === 'HEAD' ? undefined : output);
              });
            },
          );
          proxy.on('timeout', () => proxy.destroy());
          proxy.on('error', () => fail(res, 502));
          proxy.end(body);
        });
      });
    },
  };
}
