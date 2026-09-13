import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig} from 'vite';

// Hostnames the dev/preview server is allowed to answer for.
//
// Vite's default allowlist only permits localhost, `.localhost` and raw IPs, so
// a reverse-proxied preview host is rejected with HTTP 403 ("Blocked request.
// This host is not allowed."). The Arena/E2B preview serves this UI from
// https://{port}-{sandboxId}.e2b.app, hence the `.e2b.app` suffix below (a
// leading dot matches the domain and all of its subdomains).
//
// Override with VITE_ALLOWED_HOSTS (comma-separated) or set it to `true` to
// disable the check entirely. This only affects the dev/preview server.
const allowedHosts: string[] | true = (() => {
  const raw = process.env.VITE_ALLOWED_HOSTS ?? '.e2b.app';
  if (raw.trim().toLowerCase() === 'true') return true;
  return raw.split(',').map((h) => h.trim()).filter(Boolean);
})();

export default defineConfig(() => {
  return {
    build: {
      outDir: 'dist',
    },
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      host: '0.0.0.0',
      port: 3000,
      allowedHosts,
      // HMR is disabled in AI Studio via DISABLE_HMR env var.
      // Do not modify: file watching is disabled to prevent flickering during agent edits.
      hmr: process.env.DISABLE_HMR !== 'true',
      // Disable file watching when DISABLE_HMR is true to save CPU during agent edits.
      watch: process.env.DISABLE_HMR === 'true' ? null : {
        ignored: ['**/data/**']
      },
      // Real backend: FastAPI execution engine on :8000 (see bin/run.sh / docker-compose.yml)
      proxy: {
        '/api': {
          target: process.env.VITE_API_PROXY || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
    // `vite preview` (production static serve) proxies like the dev server
    preview: {
      host: '0.0.0.0',
      port: 3000,
      allowedHosts,
      proxy: {
        '/api': {
          target: process.env.VITE_API_PROXY || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  };
});
