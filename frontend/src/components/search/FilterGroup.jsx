import React from 'react';

const FilterGroup = ({
  label,
  filterType,
  values,
  selectedFilters,
  filterText,
  openDropdown,
  setFilterText,
  toggleDropdown,
  handleFilterChange,
  removeFilter,
  getDisplayValue,
  getValue
}) => {
  return (
    <div className="filter-group">
      <div className="filter-label-container">
        <label className="filter-label">{label}</label>
        {selectedFilters[filterType].length > 0 && (
          <button
            className="filter-clear-button visible"
            onClick={() => {
              handleFilterChange(filterType, []);
            }}
            aria-label={`Clear ${label} filters`}
          >
            ×
          </button>
        )}
      </div>
      <div className="filter-dropdown">
        <input
          type="text"
          className="dropdown-button filter-input"
          value={filterText[filterType]}
          onChange={(e) => setFilterText(prev => ({
            ...prev,
            [filterType]: e.target.value
          }))}
          onClick={() => toggleDropdown(filterType)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              toggleDropdown(null);
            }
          }}
          placeholder={`Filter ${label.toLowerCase()}...`}
        />
        {openDropdown === filterType && (
          <div className="dropdown-content">
            {values.filter(value => {
              const searchText = filterText[filterType].toLowerCase();
              const displayValue = getDisplayValue ? getDisplayValue(value) : value;
              return displayValue.toLowerCase().includes(searchText);
            }).map(value => {
              const displayValue = getDisplayValue ? getDisplayValue(value) : value;
              const selectedValue = getValue ? getValue(value) : value;
              return (
                <div 
                  key={value}
                  className={`dropdown-item ${selectedFilters[filterType].includes(selectedValue) ? 'selected' : ''}`}
                  onClick={() => handleFilterChange(filterType, value)}
                >
                  {displayValue}
                  {selectedFilters[filterType].includes(selectedValue) && (
                    <span className="checkmark">✓</span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
      <div className="selected-filters">
        {selectedFilters[filterType].map(value => {
          const displayValue = filterType === 'selected_subject'
            ? getDisplayValue(value)
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
  );
};

export default FilterGroup;
