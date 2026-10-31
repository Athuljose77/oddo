import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Proxy API requests to the FastAPI backend running on port 8000
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
        // Remove /api prefix before forwarding to backend
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
})
