# frontend/Dockerfile
FROM node:20-slim

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

CMD ["npm", "run", "dev"]

# frontend/package.json
{
  "name": "frontend",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "axios": "^1.6.2"
  },
  "devDependencies": {
    "@types/react": "^18.2.43",
    "@types/react-dom": "^18.2.17",
    "@vitejs/plugin-react": "^4.2.1",
    "vite": "^5.0.8"
  }
}

# frontend/vite.config.js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000
  }
})

# frontend/src/App.jsx
import { useState, useEffect } from 'react'
import axios from 'axios'

function App() {
  const [message, setMessage] = useState('')
  const apiUrl = import.meta.env.VITE_API_URL

  useEffect(() => {
    axios.get(`${apiUrl}/api/hello`)
      .then(response => setMessage(response.data.message))
      .catch(error => console.error('Error:', error))
  }, [])

  return (
    <div className="App">
      <h1>Frontend App</h1>
      <p>Message from backend: {message}</p>
    </div>
  )
}

export default App
