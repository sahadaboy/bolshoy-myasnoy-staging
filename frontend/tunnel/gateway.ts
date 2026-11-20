import { readdirSync, existsSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { get, type IncomingMessage, type ServerResponse } from 'node:http';
import type { Plugin, ProxyOptions } from 'vite';
import { allowedRequestHost, publicHeaders, publicRoute } from './policy';

const API_MARKER = 'x-miniapp-public-api';
const MAX_JSON = 512 * 1024;
const MAX_IMAGE = 16 * 1024 * 1024;

/** Only intentionally published build files, never arbitrary public/repository files. */
export function publicFiles(dist: string): Set<string> {
  const files = new Set<string>();
  for (const path of ['index.html', 'boot.js', 'boot.css', 'brand-logo-original.png', 'image-credits.txt', 'fonts/Manrope-OFL.txt']) {
    if (existsSync(join(dist, path))) files.add(`/${path}`);
  }
  for (const folder of ['assets', 'categories']) {
    if (!existsSync(join(dist, folder))) continue;
    for (const file of readdirSync(join(dist, folder), { withFileTypes: true })) {
      const allowed = folder === 'assets'
        ? /^[a-z0-9][a-z0-9._-]*\.(?:js|css|woff2?|png|jpe?g|webp|svg|avif)$/i.test(file.name)
        : /^[a-z0-9][a-z0-9_-]*\.webp$/i.test(file.name);
      if (file.isFile() && allowed) files.add(`/${folder}/${file.name}`);
    }
  }
  return files;
}

function jsonError(res: ServerResponse, status = 502): void {
  if (res.headersSent || res.writableEnded) return;
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.end(JSON.stringify({ detail: status === 404 ? 'Not found.' : status === 405 ? 'Method not allowed.' : status === 403 ? 'Host not allowed.' : 'Сервис временно недоступен.' }));
}

export async function requirePublicBackend(target = 'http://127.0.0.1:8002'): Promise<void> {
  await new Promise<void>((resolveRequest, reject) => {
    const request = get(`${target}/api/categories/`, { headers: { Accept: 'application/json' }, timeout: 5000 }, (response) => {
      response.resume();
      if (response.statusCode === 200 && response.headers[API_MARKER] === '1' && String(response.headers['content-type']).startsWith('application/json')) resolveRequest();
      else reject(new Error('Публичный preview требует frontend/public_backend.py на 127.0.0.1:8002. Обычный dev_backend.py публиковать нельзя.'));
    });
    request.on('timeout', () => request.destroy(new Error('Тестовый read-only backend на 8002 не отвечает.')));
    request.on('error', reject);
  });
}

/** Verify the backend on every response; never forward HTML/debug pages/cookies. */
function relay(response: IncomingMessage, request: IncomingMessage, destination: ServerResponse): void {
  const isApi = request.url?.startsWith('/api/');
  const type = String(response.headers['content-type'] || '').split(';')[0].trim().toLowerCase();
  const status = response.statusCode || 502;
  if (response.headers[API_MARKER] !== '1' || status >= 500 || status < 200 || status >= 400 && !isApi || status >= 300 && status < 400 || response.headers['content-encoding'] && response.headers['content-encoding'] !== 'identity' || (isApi ? type !== 'application/json' : !/^image\/(?:png|jpeg|webp|avif|gif)$/.test(type))) {
    response.resume();
    jsonError(destination);
    return;
  }
  const chunks: Buffer[] = [];
  let size = 0;
  let failed = false;
  const limit = isApi ? MAX_JSON : MAX_IMAGE;
  response.on('data', (chunk: Buffer) => {
    size += chunk.length;
    if (size > limit) {
      failed = true;
      response.destroy();
      jsonError(destination);
    } else chunks.push(chunk);
  });
  response.on('error', () => { failed = true; jsonError(destination); });
  response.on('aborted', () => { failed = true; jsonError(destination); });
  response.on('end', () => {
    if (failed || destination.writableEnded) return;
    const body = Buffer.concat(chunks);
    if (isApi) {
      try { JSON.parse(body.toString('utf8')); } catch { jsonError(destination); return; }
    }
    destination.statusCode = status;
    destination.setHeader('Content-Type', isApi ? 'application/json; charset=utf-8' : type);
    destination.setHeader('Cache-Control', isApi ? 'no-store' : 'public, max-age=300');
    destination.setHeader('Content-Length', body.length);
    destination.end(request.method === 'HEAD' ? undefined : body);
  });
}

export function publicProxy(target = 'http://127.0.0.1:8002'): Record<string, ProxyOptions> {
  const options: ProxyOptions = {
    target,
    changeOrigin: true,
    ws: false,
    xfwd: false,
    followRedirects: false,
    selfHandleResponse: true,
    proxyTimeout: 5000,
    timeout: 10000,
    configure(proxy) {
      proxy.on('proxyReq', (request) => {
        for (const name of ['cookie', 'authorization', 'proxy-authorization', 'origin', 'x-forwarded-host', 'x-forwarded-proto', 'x-forwarded-for']) request.removeHeader(name);
        request.setHeader('Accept-Encoding', 'identity');
      });
      proxy.on('proxyRes', relay);
      proxy.on('error', (_error, _request, response) => { if ('setHeader' in response) jsonError(response as ServerResponse); });
    },
  };
  return { '/api/': options, '/media/': options };
}

export function publicGateway(hostname: string, backendTarget = 'http://127.0.0.1:8002'): Plugin {
  let dist: string;
  return {
    name: 'miniapp-public-test-boundary',
    configResolved(config) { dist = resolve(config.root, config.build.outDir); },
    configureServer() { throw new Error('Режим tunnel предназначен только для production preview. Используйте pnpm tunnel:serve после pnpm build.'); },
    async configurePreviewServer(server) {
      if (!existsSync(join(dist, 'index.html'))) throw new Error('Сначала выполните pnpm build.');
      await requirePublicBackend(backendTarget);
      const files = publicFiles(dist);
      server.middlewares.use((request, response, next) => {
        for (const [name, value] of Object.entries(publicHeaders)) response.setHeader(name, value);
        if (!allowedRequestHost(request.headers.host, hostname)) { jsonError(response, 403); return; }
        const route = publicRoute(request.url || '', files);
        if (!route) { jsonError(response, 404); return; }
        if (request.method !== 'GET' && !(request.method === 'HEAD' && route !== 'api')) {
          response.setHeader('Allow', route === 'api' ? 'GET' : 'GET, HEAD');
          jsonError(response, 405);
          return;
        }
        response.setHeader('Cache-Control', 'no-store');
        next();
      });
    },
  };
}
