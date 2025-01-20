import React from 'react';

const NumResultsInput = ({ numResults, setNumResults, handleSearch }) => {
  const handleNumResultsChange = (e) => {
    setNumResults(e.target.value);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  return (
    <div className="filter-group">
      <label className="filter-label">Results (5-500)</label>
      <input
        type="number"
        value={numResults}
        onChange={handleNumResultsChange}
        onKeyDown={handleKeyDown}
        className="results-input"
      />
    </div>
  );
};

export default NumResultsInput;
