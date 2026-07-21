import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'serve-training-html-at-root',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (req.url === '/' || req.url === '/index.html') {
            req.url = '/training.html'
          }
          next()
        })
      }
    }
  ],
  server: {
    host: '0.0.0.0',
    port: 5174,
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/auth': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: process.env.VITE_WS_URL || 'ws://localhost:8000',
        ws: true,
      },
      '/stream': {
        target: process.env.VITE_STREAM_BASE_URL || 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist-training',
    sourcemap: true,
  },
})
