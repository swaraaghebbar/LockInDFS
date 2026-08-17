import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Proxy all /api/* requests → coordinator at :8000
      // Phase 13: coordinator now runs over HTTPS (TLS). Use https:// target
      // and secure: false to accept the self-signed dev certificate.
      // Without this the proxy opens an HTTP connection to an HTTPS server
      // and gets an immediate "socket hang up".
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,          // accept self-signed TLS cert
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/auth/callback': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
