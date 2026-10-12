import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    // Desenvolvimento: `npm run dev` com o container rodando na porta 8000
    proxy: { '/api': process.env.API_URL || 'http://localhost:8000' },
  },
  build: {
    target: 'es2020',
    sourcemap: false,
  },
})
