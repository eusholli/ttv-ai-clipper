import { useState, useEffect } from 'react'
import axios from 'axios'

function App() {
  const [message, setMessage] = useState('')

  useEffect(() => {
    axios.get('/api/hello')
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
