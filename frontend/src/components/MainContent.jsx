import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { SearchSection } from './search';
import { ResultsList } from './results';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL;

const MainContent = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedClips, setSelectedClips] = useState([]);
  const [filters, setFilters] = useState({
    speakers: [],
    dates: [],
    titles: [],
    companies: [],
    subjects: {}
  });
  const [selectedFilters, setSelectedFilters] = useState({
    selected_speaker: [],
    selected_date: [],
    selected_title: [],
    selected_company: [],
    selected_subject: []
  });
  const [numResults, setNumResults] = useState(5);
  const location = useLocation();

  // Expose state to window for button components access
  window.searchQuery = searchQuery;
  window.selectedFilters = selectedFilters;
  window.numResults = numResults;

  // Save search state before unmounting
  useEffect(() => {
    return () => {
      if (searchQuery || Object.values(selectedFilters).some(arr => arr.length > 0) || numResults !== 5) {
        sessionStorage.setItem('searchState', JSON.stringify({
          searchQuery,
          selectedFilters,
          numResults
        }));
      }
    };
  }, [searchQuery, selectedFilters, numResults]);

  // Restore search state on mount
  useEffect(() => {
    const savedState = sessionStorage.getItem('searchState');
    if (savedState) {
      const state = JSON.parse(savedState);
      setSearchQuery(state.searchQuery || '');
      setSelectedFilters(state.selectedFilters || {
        selected_speaker: [],
        selected_date: [],
        selected_title: [],
        selected_company: [],
        selected_subject: []
      });
      setNumResults(state.numResults || 5);
      
      // Only clear storage if we're on the main page
      if (location.pathname === '/') {
        sessionStorage.removeItem('searchState');
        // Perform search with restored state
        setTimeout(() => {
          handleSearch();
        }, 0);
      }
    }
  }, []);

  // Trigger search when filters change
  useEffect(() => {
    if (Object.values(selectedFilters).some(arr => arr.length > 0)) {
      handleSearch();
    }
  }, [selectedFilters]);

  // Fetch available filters on component mount with retry logic
  useEffect(() => {
    const fetchFilters = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/api/filters`);
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`Status: ${response.status}\nMessage: ${errorText}`);
        }
        const data = await response.json();
        setFilters(data);
        setIsLoading(false);
      } catch (err) {
        console.error('Error fetching filters:', err);
        // Retry after 1 second
        setTimeout(fetchFilters, 1000);
      }
    };

    setIsLoading(true);
    fetchFilters();
  }, []);

  // Validate and adjust number of results
  const validateNumResults = (value) => {
    const num = parseInt(value) || 5;
    if (num < 5) return 5;
    if (num > 500) return 500;
    return num;
  };

  // Handle search
  const handleSearch = async () => {
    try {
      setIsLoading(true);
      setSelectedClips([]); // Reset selected clips when performing new search
      const validatedResults = validateNumResults(numResults);
      if (validatedResults !== numResults) {
        setNumResults(validatedResults);
      }

      const response = await fetch(`${BACKEND_URL}/api/search`, {
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
  };

  // Get subject display string
  const getSubjectDisplayString = (value) => {
    const entry = Object.entries(filters.subjects).find(([_, v]) => v === value);
    return entry ? entry[0] : value;
  };

  return (
    <div className="container">
      <h1 className="main-title">Telecom TV AI Clipper</h1>
      
      {isLoading ? (
        <div className="loading-container">
          <div className="spinner" />
          <div className="loading-text">AI is Loading</div>
        </div>
      ) : (
        <>
          <SearchSection
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            selectedFilters={selectedFilters}
            setSelectedFilters={setSelectedFilters}
            numResults={numResults}
            setNumResults={setNumResults}
            handleSearch={handleSearch}
            filters={filters}
          />

          <ResultsList
            searchResults={searchResults}
            selectedClips={selectedClips}
            setSelectedClips={setSelectedClips}
            getSubjectDisplayString={getSubjectDisplayString}
          />
        </>
      )}
    </div>
  );
};

export default MainContent;
