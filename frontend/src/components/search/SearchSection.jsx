import React, { useState, useEffect, useRef } from 'react';
import SearchInput from './SearchInput';
import FilterGroup from './FilterGroup';
import NumResultsInput from './NumResultsInput';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL;

const SearchSection = ({ 
  searchQuery, 
  setSearchQuery,
  selectedFilters,
  setSelectedFilters,
  numResults,
  setNumResults,
  handleSearch,
  filters
}) => {
  const [openDropdown, setOpenDropdown] = useState(null);
  const [filterText, setFilterText] = useState({
    selected_speaker: '',
    selected_date: '',
    selected_title: '',
    selected_company: '',
    selected_subject: ''
  });
  const filtersRef = useRef(null);

  // Handle clicks outside filters
  useEffect(() => {
    function handleClickOutside(event) {
      const filterDropdowns = document.querySelectorAll('.filter-dropdown');
      let clickedInsideDropdown = false;
      
      filterDropdowns.forEach(dropdown => {
        if (dropdown.contains(event.target)) {
          clickedInsideDropdown = true;
        }
      });

      if (!clickedInsideDropdown && openDropdown) {
        setOpenDropdown(null);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [openDropdown]);

  // Add global keyboard event listener for Escape key
  useEffect(() => {
    const handleEscapeKey = (e) => {
      if (e.key === 'Escape' && openDropdown) {
        setOpenDropdown(null);
      }
    };

    document.addEventListener('keydown', handleEscapeKey);
    return () => {
      document.removeEventListener('keydown', handleEscapeKey);
    };
  }, [openDropdown]);

  // Toggle dropdown
  const toggleDropdown = (dropdownName) => {
    setOpenDropdown(openDropdown === dropdownName ? null : dropdownName);
  };

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

      return { ...prev, [filterType]: newValues };
    });
  };

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
  };

  // Get subject display string
  const getSubjectDisplayString = (value) => {
    const entry = Object.entries(filters.subjects).find(([_, v]) => v === value);
    return entry ? entry[0] : value;
  };

  const filterMappings = {
    selected_speaker: { label: 'Speakers', values: filters.speakers },
    selected_date: { label: 'Dates', values: filters.dates },
    selected_title: { label: 'Video Titles', values: filters.titles },
    selected_company: { label: 'Companies', values: filters.companies },
    selected_subject: { 
      label: 'Subjects', 
      values: Object.keys(filters.subjects || {}),
      getDisplayValue: (key) => key,
      getValue: (key) => filters.subjects[key]
    }
  };

  return (
    <section className="search-section">
      <SearchInput 
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        handleSearch={handleSearch}
      />

      <div className="filters-container" ref={filtersRef}>
        {Object.entries(filterMappings).map(([filterType, { label, values, getDisplayValue, getValue }]) => (
          <FilterGroup
            key={filterType}
            label={label}
            filterType={filterType}
            values={values}
            selectedFilters={selectedFilters}
            filterText={filterText}
            openDropdown={openDropdown}
            setFilterText={setFilterText}
            toggleDropdown={toggleDropdown}
            handleFilterChange={handleFilterChange}
            removeFilter={removeFilter}
            getDisplayValue={getDisplayValue}
            getValue={getValue}
          />
        ))}

        <NumResultsInput
          numResults={numResults}
          setNumResults={setNumResults}
          handleSearch={handleSearch}
        />
      </div>
    </section>
  );
};

export default SearchSection;
