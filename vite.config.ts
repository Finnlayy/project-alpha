import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig} from 'vite';

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
      proxy: {
        '/api': {
          target: process.env.VITE_API_PROXY || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  };
});
