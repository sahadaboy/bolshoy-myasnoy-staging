import { afterEach, describe, expect, it } from 'vitest';
import { createServer, request as httpRequest, type Server } from 'node:http';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { AddressInfo } from 'node:net';
import { preview, type PreviewServer } from 'vite';
import { publicGateway, publicProxy, requirePublicBackend } from './gateway';

const HOST = 'qa-only.trycloudflare.com';
let frontend: PreviewServer | undefined;
let backend: Server | undefined;
let workspace: string | undefined;
const close = (server: Server) => new Promise<void>((resolve) => server.close(() => resolve()));

afterEach(async () => {
  await frontend?.close(); frontend = undefined;
  if (backend) await close(backend); backend = undefined;
  if (workspace) await rm(workspace, { recursive: true, force: true }); workspace = undefined;
});

async function fixture() {
  let backendRequests = 0;
  let mode: 'safe' | 'debug' | 'oversized' = 'safe';
  let cookieReceived: string | undefined;
  backend = createServer((request, response) => {
    backendRequests++;
    cookieReceived = request.headers.cookie;
    if (mode === 'debug') { response.setHeader('Content-Type', 'text/html'); response.end('PRIVATE_DEBUG_SENTINEL'); return; }
    response.setHeader('X-Miniapp-Public-Api', '1');
    response.setHeader('Content-Type', 'application/json');
    response.setHeader('Set-Cookie', 'private-session=do-not-forward');
    response.end(JSON.stringify({ count: 0, results: [], ...(mode === 'oversized' ? { description: 'x'.repeat(600_000) } : {}) }));
  });
  await new Promise<void>((resolve) => backend!.listen(0, '127.0.0.1', resolve));
  const backendUrl = `http://127.0.0.1:${(backend.address() as AddressInfo).port}`;
  workspace = await mkdtemp(join(tmpdir(), 'miniapp-public-preview-'));
  const dist = join(workspace, 'dist');
  await mkdir(join(dist, 'assets'), { recursive: true });
  await writeFile(join(dist, 'index.html'), '<!doctype html><h1>Public build</h1>');
  await writeFile(join(dist, 'assets', 'app-123.js'), 'console.log("public compiled code")');
  await writeFile(join(dist, 'private-secret.txt'), 'PRIVATE_FILE_SENTINEL');
  await writeFile(join(dist, 'assets', 'app-123.js.map'), 'PRIVATE_SOURCE_MAP_SENTINEL');
  await writeFile(join(workspace, '.env'), 'PRIVATE_ENV_SENTINEL');
  frontend = await preview({
    configFile: false, root: workspace, publicDir: false,
    build: { outDir: 'dist' },
    plugins: [publicGateway(HOST, backendUrl)],
    preview: { host: '127.0.0.1', port: 0, strictPort: false, allowedHosts: [HOST], cors: false, proxy: publicProxy(backendUrl) },
  });
  const base = `http://127.0.0.1:${(frontend.httpServer.address() as AddressInfo).port}`;
  // Node fetch may discard Host overrides. Use HTTP directly to exercise the
  // same Host header cloudflared forwards, including deliberately invalid ones.
  const request = (path: string, options: RequestInit = {}) => new Promise<Response>((resolve, reject) => {
    const headers = Object.fromEntries(new Headers(options.headers).entries());
    const outgoing = httpRequest(`${base}${path}`, { method: options.method || 'GET', headers: { host: HOST, ...headers } }, (incoming) => {
      const chunks: Buffer[] = [];
      incoming.on('data', (chunk: Buffer) => chunks.push(chunk));
      incoming.on('error', reject);
      incoming.on('end', () => {
        const responseHeaders = new Headers();
        for (const [name, value] of Object.entries(incoming.headers)) {
          if (value !== undefined) responseHeaders.set(name, Array.isArray(value) ? value.join(', ') : value);
        }
        resolve(new Response(Buffer.concat(chunks).toString('utf8'), { status: incoming.statusCode, headers: responseHeaders }));
      });
    });
    outgoing.on('error', reject);
    outgoing.end();
  });
  return { request, backendUrl, get requests() { return backendRequests; }, get cookie() { return cookieReceived; }, setMode(value: typeof mode) { mode = value; } };
}

describe('actual Vite preview public boundary', () => {
  it('serves the built SPA and safe API while denying repository/admin/debug paths before proxying', async () => {
    const app = await fixture();
    const page = await app.request('/catalog');
    expect(page.status).toBe(200);
    expect(page.headers.get('x-miniapp-public-gateway')).toBe('1');
    expect(page.headers.get('content-security-policy')).toContain('https://telegram.org');
    expect(await page.text()).toContain('Public build');
    const initialRequests = app.requests;
    for (const path of ['/admin/', '/db.sqlite3', '/.env', '/private-secret.txt', '/@vite/client', '/src/main.tsx', '/@fs/C:/private/settings.py', '/assets/app-123.js.map', '/api/orders/']) {
      const response = await app.request(path);
      expect(response.status, path).toBe(404);
      expect(await response.text()).not.toMatch(/PRIVATE_/);
    }
    expect(app.requests).toBe(initialRequests);
    const api = await app.request('/api/products/', { headers: { Cookie: 'existing-admin-session=private' } });
    expect(api.status).toBe(200);
    expect(await api.json()).toMatchObject({ count: 0, results: [] });
    expect(api.headers.get('set-cookie')).toBeNull();
    expect(app.cookie).toBeUndefined();
  });

  it('rejects other hosts and write methods without reaching Django', async () => {
    const app = await fixture();
    const count = app.requests;
    expect((await app.request('/catalog', { headers: { Host: 'other.trycloudflare.com' } })).status).toBe(403);
    for (const method of ['POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD']) expect((await app.request('/api/products/', { method })).status).toBe(405);
    expect((await app.request('/catalog', { method: 'HEAD' })).status).toBe(200);
    expect(app.requests).toBe(count);
  });

  it('refuses an accidental debug backend and never relays its HTML or oversized JSON', async () => {
    const app = await fixture();
    app.setMode('debug');
    await expect(requirePublicBackend(app.backendUrl)).rejects.toThrow('public_backend.py');
    const debug = await app.request('/api/products/');
    expect(debug.status).toBe(502);
    expect(await debug.text()).not.toContain('PRIVATE_DEBUG_SENTINEL');
    app.setMode('oversized');
    expect((await app.request('/api/products/')).status).toBe(502);
  });
});
