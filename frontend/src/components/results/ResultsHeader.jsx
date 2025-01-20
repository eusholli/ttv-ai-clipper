import React from 'react';
import { EmailAllButton, UnselectAllButton } from '../buttons';

const ResultsHeader = ({ selectedClips, setSelectedClips }) => {
  return (
    <div className="email-all-container">
      <UnselectAllButton 
        selectedClips={selectedClips}
        setSelectedClips={setSelectedClips}
      />
      <EmailAllButton 
        selectedClips={selectedClips}
      />
    </div>
  );
};

export default ResultsHeader;
