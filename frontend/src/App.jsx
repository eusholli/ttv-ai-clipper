import { useState, useEffect, useRef } from 'react'
import { BrowserRouter as Router, Routes, Route, useNavigate, Navigate } from 'react-router-dom'
import { ClerkProvider, SignedIn, useAuth, useUser } from '@clerk/clerk-react'
import './styles.css'
import axios from 'axios'

// Auth Components
import SignInPage from './components/auth/SignIn'
import SignUpPage from './components/auth/SignUp'
import UserProfilePage from './components/auth/UserProfile'
import Navigation from './components/auth/Navigation'
import Pricing from './components/pricing/Pricing'

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

// Download Button Component
const DownloadButton = ({ result, downloading, setDownloading }) => {
  const { isSignedIn, getToken } = useAuth();
  const { user } = useUser();
  const navigate = useNavigate();

  const handleDownload = async () => {
    if (!isSignedIn) {
      // Save current search state before redirecting
      const searchState = {
        searchQuery: window.searchQuery,
        selectedFilters: window.selectedFilters,
        numResults: window.numResults
      };
      localStorage.setItem('searchState', JSON.stringify(searchState));
      navigate('/sign-in');
      return;
    }

    try {
      // Check subscription status first
      const token = await getToken();
      const stripeCustomerId = user?.unsafeMetadata?.stripeCustomerId;
      
      if (!stripeCustomerId) {
        navigate('/user-profile');
        return;
      }

      const response = await axios.get(`/api/subscription-status?customer_id=${stripeCustomerId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (response.data.status !== 'active') {
        navigate('/user-profile');
        return;
      }

      setDownloading({ ...downloading, [result.segment_hash]: true });
      
      const downloadResponse = await fetch(`/api/download/${result.segment_hash}`);
      if (!downloadResponse.ok) {
        const errorText = await downloadResponse.text();
        throw new Error(`Status: ${downloadResponse.status}\nMessage: ${errorText}`);
      }
      
      const blob = await downloadResponse.blob();
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
      if (err.response?.status === 403) {
        navigate('/pricing');
      } else {
        alert(`Failed to download clip:\n${err.message}`);
      }
    } finally {
      setDownloading({ ...downloading, [result.segment_hash]: false });
    }
  };

  return (
    <button
      className="download-button"
      onClick={handleDownload}
      disabled={downloading[result.segment_hash]}
    >
      <DownloadIcon />
      {downloading[result.segment_hash] ? 'Downloading...' : 
       !isSignedIn ? 'Subscribe to Download' : 'Download Clip'}
    </button>
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
    companies: [],
    subjects: {}
  })
  const [selectedFilters, setSelectedFilters] = useState({
    selected_speaker: [],
    selected_date: [],
    selected_title: [],
    selected_company: [],
    selected_subject: []
  })
  const [numResults, setNumResults] = useState(5)
  const [openDropdown, setOpenDropdown] = useState(null)
  const [downloading, setDownloading] = useState({})
  const filtersRef = useRef(null)
  const { isSignedIn } = useAuth();

  // Expose state to window for DownloadButton access
  window.searchQuery = searchQuery;
  window.selectedFilters = selectedFilters;
  window.numResults = numResults;

  // Restore search state after sign-in
  useEffect(() => {
    if (isSignedIn) {
      const savedState = localStorage.getItem('searchState');
      if (savedState) {
        const { searchQuery: savedQuery, selectedFilters: savedFilters, numResults: savedResults } = JSON.parse(savedState);
        setSearchQuery(savedQuery);
        setSelectedFilters(savedFilters);
        setNumResults(savedResults);
        localStorage.removeItem('searchState'); // Clear saved state
      }
    }
  }, [isSignedIn]);

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

  // Effect to trigger search when filters change or when restored from localStorage
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

  // Format seconds to HH:MM:SS
  const formatSecondsToTime = (seconds) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = seconds % 60;
    
    if (hours > 0) {
      return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
    }
    return `${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
  }

  // Handle filter selection
  const handleFilterChange = (filterType, value) => {
    setSelectedFilters(prev => {
      const currentValues = prev[filterType];
      let newValues;

      if (filterType === 'selected_subject') {
        // For subjects, we store the display string in the UI but use the value for filtering
        const subjectValue = filters.subjects[value];
        const valueIndex = currentValues.indexOf(subjectValue);
        newValues = valueIndex === -1
          ? [...currentValues, subjectValue]
          : currentValues.filter((_, index) => index !== valueIndex);
      } else {
        const valueIndex = currentValues.indexOf(value);
        newValues = valueIndex === -1
          ? [...currentValues, value]
          : currentValues.filter((_, index) => index !== valueIndex);
      }

      setOpenDropdown(null);
      return { ...prev, [filterType]: newValues };
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
    setSelectedFilters(prev => {
      if (filterType === 'selected_subject') {
        // For subjects, we need to find the display string that matches this value
        const displayString = Object.entries(filters.subjects)
          .find(([_, v]) => v === value)?.[0];
        if (!displayString) return prev;
      }
      return {
        ...prev,
        [filterType]: prev[filterType].filter(item => item !== value)
      };
    });
  }

  const filterMappings = {
    selected_speaker: { label: 'Speakers', values: filters.speakers },
    selected_date: { label: 'Dates', values: filters.dates },
    selected_title: { label: 'Titles', values: filters.titles },
    selected_company: { label: 'Companies', values: filters.companies },
    selected_subject: { 
      label: 'Subjects', 
      values: Object.keys(filters.subjects || {}),
      getDisplayValue: (key) => key,
      getValue: (key) => filters.subjects[key]
    }
  }

  // Handle key press for search input
  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  }

  // Get display string for a subject value
  const getSubjectDisplayString = (value) => {
    const entry = Object.entries(filters.subjects).find(([_, v]) => v === value);
    return entry ? entry[0] : value;
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
          {Object.entries(filterMappings).map(([filterType, { label, values, getDisplayValue }]) => (
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
                    {values.map(value => {
                      const displayValue = getDisplayValue ? getDisplayValue(value) : value;
                      const selectedValue = filterType === 'selected_subject' 
                        ? filters.subjects[value]
                        : value;
                      return (
                        <div 
                          key={value}
                          className={`dropdown-item ${selectedFilters[filterType].includes(selectedValue) ? 'selected' : ''}`}
                          onClick={() => handleFilterChange(filterType, value)}
                        >
                          {displayValue}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
              <div className="selected-filters">
                {selectedFilters[filterType].map(value => {
                  const displayValue = filterType === 'selected_subject'
                    ? getSubjectDisplayString(value)
                    : value;
                  return (
                    <span 
                      key={value} 
                      className="filter-tag"
                      onClick={() => removeFilter(filterType, value)}
                    >
                      {displayValue} ×
                    </span>
                  );
                })}
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
            const startParam = result.start_time === 0 ? "0" : result.start_time - 1
            const endParam = result.end_time === 0 ? "" : `&end=${result.end_time + 1}`
            const ytUrl = `https://youtube.com/embed/${result.youtube_id}?start=${startParam}${endParam}&autoplay=0&rel=0`

            return (
              <article key={index} className="result-item">
                <div className="result-content">
                  <h2 className="result-title">{result.title}</h2>
                  <div className="result-meta">
                    {result.speaker} · {result.company}
                  </div>
                  <div className="result-time">
                    {formatSecondsToTime(result.start_time)} - {formatSecondsToTime(result.end_time)} · {result.date.split('T')[0]}
                    <span className="result-score">Match Score: {(result.score * 100).toFixed(1)}%</span>
                  </div>
                  <p className="result-text">{result.text}</p>
                  {result.subjects && (
                    <div className="result-tags">
                      Tags: {result.subjects.map(subject => getSubjectDisplayString(subject)).join(', ')}
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
                    <DownloadButton 
                      result={result}
                      downloading={downloading}
                      setDownloading={setDownloading}
                    />
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
  
  console.log('import.meta.env:', import.meta.env)
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
            <Route path="/" element={<MainContent />} />
            <Route path="/sign-in/*" element={<SignInPage />} />
            <Route path="/sign-up/*" element={<SignUpPage />} />
            <Route path="/pricing" element={<Pricing />} />
            <Route 
              path="/user-profile/*" 
              element={
                <ProtectedRoute>
                  <UserProfilePage />
                </ProtectedRoute>
              } 
            />
            {/* Add redirect from /profile to /user-profile */}
            <Route 
              path="/profile" 
              element={
                <ProtectedRoute>
                  <Navigate to="/user-profile" replace />
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
