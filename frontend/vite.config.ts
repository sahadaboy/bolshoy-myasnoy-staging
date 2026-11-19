import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { publicGateway, publicProxy } from './tunnel/gateway';
import { tunnelHostname } from './tunnel/policy';
import { liveGateway } from './tunnel/live';

export default defineConfig(({ mode }) => {
  const hostname = tunnelHostname(process.env.MINIAPP_TUNNEL_HOST);
  const isPublicTest = mode === 'tunnel';
  const isLive = mode === 'live';
  const liveHost = process.env.MINIAPP_LIVE_HOST || '';
  if (isPublicTest && !hostname)
    throw new Error('Задайте MINIAPP_TUNNEL_HOST — точный hostname текущего Quick Tunnel.');
  const target = process.env.VITE_API_TARGET || 'http://127.0.0.1:8001';
  const localProxy = {
    '/api': { target, changeOrigin: true },
    '/media': { target, changeOrigin: true },
  };
  return {
    plugins: [
      react(),
      tailwindcss(),
      ...(isPublicTest ? [publicGateway(hostname!)] : []),
      ...(isLive ? [liveGateway(liveHost, target)] : []),
    ],
    build: { sourcemap: false },
    server: {
      host: '127.0.0.1',
      port: 5174,
      strictPort: true,
      allowedHosts: isLive ? [liveHost] : hostname ? [hostname] : [],
      proxy: localProxy,
    },
    preview: {
      host: '127.0.0.1',
      port: 5174,
      strictPort: true,
      allowedHosts: isLive ? [liveHost] : hostname ? [hostname] : [],
      cors: false,
      proxy: isLive ? undefined : isPublicTest ? publicProxy() : localProxy,
    },
  };
});
