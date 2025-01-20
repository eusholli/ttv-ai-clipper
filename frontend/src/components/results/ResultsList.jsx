import React, { useState } from 'react';
import ResultsHeader from './ResultsHeader';
import ResultItem from './ResultItem';

const ResultsList = ({ 
  searchResults, 
  selectedClips, 
  setSelectedClips,
  getSubjectDisplayString 
}) => {
  const [downloading, setDownloading] = useState({});
  const [emailing, setEmailing] = useState({});

  if (!searchResults.length) {
    return null;
  }

  return (
    <div className="search-results">
      <ResultsHeader 
        selectedClips={selectedClips}
        setSelectedClips={setSelectedClips}
      />
      {searchResults.map((result, index) => (
        <ResultItem
          key={index}
          result={result}
          selectedClips={selectedClips}
          setSelectedClips={setSelectedClips}
          downloading={downloading}
          setDownloading={setDownloading}
          emailing={emailing}
          setEmailing={setEmailing}
          getSubjectDisplayString={getSubjectDisplayString}
        />
      ))}
    </div>
  );
};

export default ResultsList;
