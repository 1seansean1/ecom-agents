import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8060',
      '/ws': {
        target: 'http://localhost:8060',
        ws: true,
      },
      '/chat-ui': {
        target: 'http://localhost:8073',
        rewrite: (path) => path.replace(/^\/chat-ui/, ''),
        changeOrigin: true,
      },
    },
  },
})
