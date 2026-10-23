import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Em desenvolvimento o Vite repassa /api para o FastAPI (porta 8000).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
