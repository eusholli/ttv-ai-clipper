import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {

  return {
    plugins: [react()],
    server: {
      host: true,
      port: 5173,
      cors: true,
      proxy: {
        '/api': {
          target: 'http://0.0.0.0:8000',
          changeOrigin: true,
          secure: false,
          ws: true
        }
      }
    }
  }
})
