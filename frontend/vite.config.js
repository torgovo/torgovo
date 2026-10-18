import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Dedicated torgovo2 frontend port (2026-10-18). strictPort: fail loudly
    // instead of silently drifting to another port when occupied.
    port: 5175,
    strictPort: true,
    proxy: {
      '/api': {
        // Dedicated torgovo2 backend port — must match BACKEND_PORT in .env
        target: 'http://127.0.0.1:8600',
        changeOrigin: true,
      }
    }
  }
})
