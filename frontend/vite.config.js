import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  
  // Load and log all env vars during build
  const env = loadEnv(mode, process.cwd(), '')
  console.log('Build Mode:', mode)
  console.log('Environment Variables:', env)
  
  return {
    plugins: [react()],
    server: {
      host: true,
      port: 5173,
      cors: true,
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          secure: false,
        }
      }
    },
  }
})
