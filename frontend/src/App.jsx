import { useState, useEffect, useRef } from 'react'
import { BrowserRouter as Router, Routes, Route, useNavigate } from 'react-router-dom'
import { ClerkProvider, SignedIn } from '@clerk/clerk-react'
import './styles.css'

// Auth Components
import SignInPage from './components/auth/SignIn'
import SignUpPage from './components/auth/SignUp'
import UserProfilePage from './components/auth/UserProfile'
import Navigation from './components/auth/Navigation'

// Download icon component
const DownloadIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
  </svg>
)

// Protected Route Component
const ProtectedRoute = ({ children }) => {
  return (
    <SignedIn>
      {children}
    </SignedIn>
  );
};

// Main Content Component
const MainContent = () => {
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [filters, setFilters] = useState({
    speakers: [],
    dates: [],
    titles: [],
    companies: []
  })
  const [selectedFilters, setSelectedFilters] = useState({
    selected_speaker: [],
    selected_date: [],
    selected_title: [],
    selected_company: []
  })
  const [numResults, setNumResults] = useState(5)
  const [openDropdown, setOpenDropdown] = useState(null)
  const [downloading, setDownloading] = useState({})
  const filtersRef = useRef(null)

  // Handle clicks outside filters
  useEffect(() => {
    function handleClickOutside(event) {
      if (filtersRef.current && !filtersRef.current.contains(event.target)) {
        setOpenDropdown(null)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [])

  // Fetch available filters on component mount
  useEffect(() => {
    fetch('/api/filters')
      .then(async response => {
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`Status: ${response.status}\nMessage: ${errorText}`);
        }
        return response.json();
      })
      .then(data => setFilters(data))
      .catch(err => {
        console.error('Error fetching filters:', err);
        alert(`Failed to fetch filters:\n${err.message}`);
      });
  }, [])

  // Effect to trigger search when filters change
  useEffect(() => {
    if (searchQuery || Object.values(selectedFilters).some(arr => arr.length > 0)) {
      handleSearch();
    }
  }, [selectedFilters]);

  // Validate and adjust number of results
  const validateNumResults = (value) => {
    const num = parseInt(value) || 5;
    if (num < 5) return 5;
    if (num > 20) return 20;
    return num;
  }

  // Handle search
  const handleSearch = async () => {
    try {
      setIsLoading(true);
      const validatedResults = validateNumResults(numResults);
      if (validatedResults !== numResults) {
        setNumResults(validatedResults);
      }

      const response = await fetch('/api/search', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: searchQuery,
          top_k: validatedResults,
          ...selectedFilters
        }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Status: ${response.status}\nMessage: ${errorText}`);
      }

      const data = await response.json();
      setSearchResults(data.results);
    } catch (err) {
      console.error('Error performing search:', err);
      alert(`Failed to perform search:\n${err.message}`);
    } finally {
      setIsLoading(false);
    }
  }

  // Handle clip download
  const handleDownload = async (result) => {
    try {
      setDownloading({ ...downloading, [result.segment_hash]: true });
      
      const response = await fetch(`/api/download/${result.segment_hash}`);
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Status: ${response.status}\nMessage: ${errorText}`);
      }
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `clip-${result.segment_hash}.mp4`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Error downloading clip:', err);
      alert(`Failed to download clip:\n${err.message}`);
    } finally {
      setDownloading({ ...downloading, [result.segment_hash]: false });
    }
  }

  // Convert timestamp to seconds
  const timestampToSeconds = (timestamp) => {
    const parts = timestamp.split(':')
    if (parts.length === 3) {
      const [h, m, s] = parts.map(Number)
      return h * 3600 + m * 60 + s
    } else if (parts.length === 2) {
      const [m, s] = parts.map(Number)
      return m * 60 + s
    } else {
      console.error(`Invalid timestamp format: ${timestamp}`)
      return 0
    }
  }

  // Format timestamp for display
  const formatTimestamp = (timestamp) => {
    const parts = timestamp.split(':')
    if (parts.length === 2) {
      return `${parts[0]}m ${parts[1]}s`
    }
    return timestamp
  }

  // Handle filter selection
  const handleFilterChange = (filterType, value) => {
    setSelectedFilters(prev => {
      const currentValues = prev[filterType]
      const valueIndex = currentValues.indexOf(value)
      
      const newFilters = valueIndex === -1
        ? { ...prev, [filterType]: [...currentValues, value] }
        : { ...prev, [filterType]: currentValues.filter((_, index) => index !== valueIndex) };
      
      setOpenDropdown(null);
      
      return newFilters;
    });
  }

  // Handle number of results change
  const handleNumResultsChange = (e) => {
    setNumResults(e.target.value);
  }

  // Handle results input key press
  const handleResultsKeyDown = (e) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  }

  // Toggle dropdown
  const toggleDropdown = (dropdownName) => {
    setOpenDropdown(openDropdown === dropdownName ? null : dropdownName)
  }

  // Remove selected filter
  const removeFilter = (filterType, value) => {
    setSelectedFilters(prev => ({
      ...prev,
      [filterType]: prev[filterType].filter(item => item !== value)
    }));
  }

  const filterMappings = {
    selected_speaker: { label: 'Speakers', values: filters.speakers },
    selected_date: { label: 'Dates', values: filters.dates },
    selected_title: { label: 'Titles', values: filters.titles },
    selected_company: { label: 'Companies', values: filters.companies }
  }

  // Handle key press for search input
  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  }

  return (
    <div className="container">
      <h1 className="main-title">Telecom TV AI Clipper</h1>
      
      {/* Search Section */}
      <section className="search-section">
        <div className="search-container">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search transcripts..."
            className="search-input"
          />
          <button onClick={handleSearch} className="search-button" disabled={isLoading}>
            {isLoading ? <div className="spinner" /> : 'Search'}
          </button>
        </div>

        <div className="filters-container" ref={filtersRef}>
          {Object.entries(filterMappings).map(([filterType, { label, values }]) => (
            <div key={filterType} className="filter-group">
              <label className="filter-label">{label}</label>
              <div className="filter-dropdown">
                <button 
                  className="dropdown-button"
                  onClick={() => toggleDropdown(filterType)}
                >
                  Select {label}
                </button>
                {openDropdown === filterType && (
                  <div className="dropdown-content">
                    {values.map(value => (
                      <div 
                        key={value}
                        className={`dropdown-item ${selectedFilters[filterType].includes(value) ? 'selected' : ''}`}
                        onClick={() => handleFilterChange(filterType, value)}
                      >
                        {value}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="selected-filters">
                {selectedFilters[filterType].map(value => (
                  <span 
                    key={value} 
                    className="filter-tag"
                    onClick={() => removeFilter(filterType, value)}
                  >
                    {value} ×
                  </span>
                ))}
              </div>
            </div>
          ))}

          <div className="filter-group">
            <label className="filter-label">Results</label>
            <input
              type="number"
              value={numResults}
              onChange={handleNumResultsChange}
              onKeyDown={handleResultsKeyDown}
              className="results-input"
            />
          </div>
        </div>
      </section>

      {/* Search Results */}
      {searchResults.length > 0 && (
        <div className="search-results">
          {searchResults.map((result, index) => {
            const stTs = timestampToSeconds(result.start_time)
            const endTs = timestampToSeconds(result.end_time)
            const startParam = stTs === 0 ? "0" : stTs - 1
            const endParam = endTs === 0 ? "" : `&end=${endTs + 1}`
            const ytUrl = `https://youtube.com/embed/${result.youtube_id}?start=${startParam}${endParam}&autoplay=0&rel=0`

            return (
              <article key={index} className="result-item">
                <div className="result-content">
                  <h2 className="result-title">{result.title}</h2>
                  <div className="result-meta">
                    {result.speaker} · {result.company}
                  </div>
                  <div className="result-time">
                    {formatTimestamp(result.start_time)} - {formatTimestamp(result.end_time)} · {result.date}
                    <span className="result-score">Match Score: {(result.score * 100).toFixed(1)}%</span>
                  </div>
                  <p className="result-text">{result.text}</p>
                  {result.subjects && (
                    <div className="result-tags">
                      Tags: {result.subjects.join(', ')}
                    </div>
                  )}
                </div>
                <div className="result-video">
                  <iframe
                    src={ytUrl}
                    width="300"
                    height="169"
                    frameBorder="0"
                    allowFullScreen
                  />
                  {result.download && (
                    <button
                      className="download-button"
                      onClick={() => handleDownload(result)}
                      disabled={downloading[result.segment_hash]}
                    >
                      <DownloadIcon />
                      {downloading[result.segment_hash] ? 'Downloading...' : 'Download Clip'}
                    </button>
                  )}
                </div>
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}

function App() {
  console.log(import.meta.env)

  const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

  if (!publishableKey) {
    console.error("Missing needed keys. Please check your environment variables.");
    return (
      <div style={{ 
        padding: '20px', 
        textAlign: 'center', 
        color: '#721c24',
        backgroundColor: '#f8d7da',
        border: '1px solid #f5c6cb',
        borderRadius: '4px',
        margin: '20px'
      }}>
        <h2>Configuration Error</h2>
        <p>The application is missing required configuration. Please contact the administrator.</p>
      </div>
    );
  }

  return (
    <ClerkProvider 
      publishableKey={publishableKey}
      routing="path"
    >
      <Router>
        <div className="App">
          <Navigation />
          <Routes>
            <Route 
              path="/" 
              element={
                <ProtectedRoute>
                  <MainContent />
                </ProtectedRoute>
              } 
            />
            <Route path="/sign-in/*" element={<SignInPage />} />
            <Route path="/sign-up/*" element={<SignUpPage />} />
            <Route 
              path="/user-profile/*" 
              element={
                <ProtectedRoute>
                  <UserProfilePage />
                </ProtectedRoute>
              } 
            />
          </Routes>
        </div>
      </Router>
    </ClerkProvider>
  )
}

export default App
