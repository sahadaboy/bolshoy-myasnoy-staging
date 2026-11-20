import { afterEach, expect, it } from 'vitest';
import {
  createServer,
  request as httpRequest,
  type Server,
  type IncomingHttpHeaders,
} from 'node:http';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, dirname, basename, resolve } from 'node:path';
import type { AddressInfo } from 'node:net';
import { preview, type PreviewServer } from 'vite';
import { liveGateway } from './live';

let frontend: PreviewServer | undefined;
let backend: Server | undefined;
let workspace: string | undefined;
let forwarded: IncomingHttpHeaders;
let forwardedBody = '';
let requests = 0;

afterEach(async () => {
  await frontend?.close();
  frontend = undefined;
  if (backend) await new Promise<void>((done) => backend!.close(() => done()));
  backend = undefined;
  if (workspace) {
    if (
      dirname(resolve(workspace)) !== resolve(tmpdir()) ||
      !basename(workspace).startsWith('miniapp-live-preview-')
    )
      throw new Error('Unexpected temporary directory');
    await rm(workspace, { recursive: true, force: true });
  }
  workspace = undefined;
});

async function fixture() {
  requests = 0;
  backend = createServer((req, res) => {
    requests++;
    forwarded = req.headers;
    const parts: Buffer[] = [];
    req.on('data', (chunk) => parts.push(chunk));
    req.on('end', () => {
      forwardedBody = Buffer.concat(parts).toString();
      res.setHeader('Content-Type', 'application/json');
      res.setHeader(
        'Set-Cookie',
        req.url === '/api/session/login/'
          ? [
              'admin-cookie=private',
              'bm_customer=fixture; HttpOnly; Secure; SameSite=Lax',
              'csrftoken=fixture; HttpOnly; Secure; SameSite=Lax',
            ]
          : 'admin-cookie=private',
      );
      res.statusCode = req.headers.authorization === 'tma expired-fixture' ? 401 : 200;
      res.end(
        JSON.stringify({
          authenticated: req.headers.authorization === 'tma signed-fixture',
          detail: 'fixture',
        }),
      );
    });
  });
  await new Promise<void>((done) => backend!.listen(0, '127.0.0.1', done));
  workspace = await mkdtemp(join(tmpdir(), 'miniapp-live-preview-'));
  await mkdir(join(workspace, 'dist'));
  await writeFile(join(workspace, 'dist/index.html'), '<!doctype html><h1>Compiled app</h1>');
  return async function start(host: string) {
    await frontend?.close();
    frontend = await preview({
      configFile: false,
      root: workspace,
      publicDir: false,
      build: { outDir: 'dist' },
      plugins: [liveGateway(host, `http://127.0.0.1:${(backend!.address() as AddressInfo).port}`)],
      preview: { host: '127.0.0.1', port: 0, strictPort: false, allowedHosts: [host], cors: false },
    });
    const port = (frontend.httpServer.address() as AddressInfo).port;
    return {
      port,
      request: (path: string, headers: Record<string, string> = {}, method = 'GET', body = '') =>
        new Promise<Response>((done, reject) => {
          const outgoing = httpRequest(
            { hostname: '127.0.0.1', port, path, method, headers: { Host: host, ...headers } },
            (incoming) => {
              const chunks: Buffer[] = [];
              incoming.on('data', (chunk) => chunks.push(chunk));
              incoming.on('error', reject);
              incoming.on('end', () => {
                const resultHeaders = new Headers();
                for (const [key, value] of Object.entries(incoming.headers))
                  if (value !== undefined)
                    resultHeaders.set(key, Array.isArray(value) ? value.join(', ') : value);
                done(
                  new Response(Buffer.concat(chunks).toString(), {
                    status: incoming.statusCode,
                    headers: resultHeaders,
                  }),
                );
              });
            },
          );
          outgoing.on('error', reject);
          outgoing.end(body);
        }),
    };
  };
}

it('forwards signed account requests through one origin, without Admin cookies or client forwarding headers', async () => {
  const start = await fixture();
  const app = await start('first-launch.example');
  const response = await app.request('/api/session/', {
    Authorization: 'tma signed-fixture',
    Cookie: 'private-cookie=1',
    'X-Forwarded-Proto': 'http',
  });
  expect(await response.json()).toMatchObject({ authenticated: true });
  expect(forwarded.authorization).toBe('tma signed-fixture');
  expect(forwarded.cookie).toBeUndefined();
  expect(forwarded['x-forwarded-proto']).toBe('https');
  expect(response.headers.get('set-cookie')).toBeNull();
  expect(response.headers.get('cache-control')).toContain('no-store');
  expect(
    (
      await app.request(
        '/api/profile/',
        { Authorization: 'tma signed-fixture', Origin: 'https://first-launch.example' },
        'PATCH',
        '{"phone":"+79780000000"}',
      )
    ).status,
  ).toBe(200);
  expect(forwardedBody).toBe('{"phone":"+79780000000"}');
  expect(
    (await app.request('/api/session/', { Authorization: 'tma expired-fixture' })).status,
  ).toBe(401);
  expect(await (await app.request('/api/session/')).json()).toMatchObject({ authenticated: false });
});

it('accepts only the configured public host and the actual loopback port, then switches hosts without API changes', async () => {
  const start = await fixture();
  const first = await start('first-launch.example');
  expect((await first.request('/profile', { Host: `127.0.0.1:${first.port}` })).status).toBe(200);
  const count = requests;
  const invalidHeaders: Record<string, string>[] = [
    { Host: 'another.example' },
    { Host: 'localhost:1' },
    { Origin: 'https://another.example' },
  ];
  for (const headers of invalidHeaders)
    expect((await first.request('/api/session/', headers)).status).toBe(403);
  expect(requests).toBe(count);
  const second = await start('second-launch.example');
  expect(
    await (await second.request('/api/session/', { Authorization: 'tma signed-fixture' })).json(),
  ).toMatchObject({ authenticated: true });
  expect((await second.request('/api/session/', { Host: 'first-launch.example' })).status).toBe(
    403,
  );
  for (const path of ['/admin/', '/.env', '/db.sqlite3', '/@fs/private', '/src/main.tsx'])
    expect((await second.request(path)).status).toBe(404);
});

it('passes only customer and CSRF cookies, retaining the Admin boundary', async () => {
  const start = await fixture();
  const app = await start('customer-login.example');
  const response = await app.request(
    '/api/session/login/',
    {
      Authorization: 'tma signed-fixture',
      Origin: 'https://customer-login.example',
      Cookie: 'sessionid=admin; private-cookie=private; bm_customer=customer; csrftoken=csrf',
      'X-CSRFToken': 'csrf',
    },
    'POST',
  );
  expect(response.status).toBe(200);
  expect(forwarded.cookie).toBe('bm_customer=customer; csrftoken=csrf');
  expect(forwarded['x-csrftoken']).toBe('csrf');
  expect(forwarded.origin).toBe('https://customer-login.example');
  expect(response.headers.get('set-cookie')).toContain('bm_customer=fixture');
  expect(response.headers.get('set-cookie')).not.toContain('admin-cookie');
  expect((await app.request('/api/cart/')).status).toBe(200);
});
