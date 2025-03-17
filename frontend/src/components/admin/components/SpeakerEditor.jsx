import { useState, useEffect } from 'react';
import './SpeakerEditor.css';

const SpeakerEditor = ({ 
  rawTranscript, 
  onTranscriptUpdate, 
  onSpeakerMappingChange,
  initialSpeakerMapping = {},
  initialCompanyMapping = {}
}) => {
  const [speakerMapping, setSpeakerMapping] = useState(initialSpeakerMapping);
  const [companyMapping, setCompanyMapping] = useState(initialCompanyMapping);
  const [previewTranscript, setPreviewTranscript] = useState('');
  
  // Extract unique speakers and companies on component mount
  useEffect(() => {
    if (!rawTranscript) return;
    
    try {
      // Extract speaker/company pairs using regex
      // Format: "Speaker Name, Company Name (00:00):" or "Speaker Name, Company Name (00:00:00):"
      // Note: Speakers are preceded by a newline character in the transcript
      const speakerPattern = /\n\n([^,]+),\s*([^(]+)\s*\(((\d{2}:\d{2}:\d{2})|(\d{2}:\d{2}))\):/gm;
      const matches = [...rawTranscript.matchAll(speakerPattern)];
      
      // Create initial mapping objects
      const speakers = {};
      const companies = {};
      
      matches.forEach(match => {
        const speakerName = match[1].trim();
        const companyName = match[2].trim();
        
        if (!speakers[speakerName]) {
          speakers[speakerName] = speakerName;
        }
        
        if (!companies[companyName]) {
          companies[companyName] = companyName;
        }
      });
      
      setSpeakerMapping(speakers);
      setCompanyMapping(companies);
      setPreviewTranscript(rawTranscript);
    } catch (error) {
      console.error("Error extracting speakers and companies:", error);
      // Optionally set an error state to display a message to the user
      // setError("Failed to extract speaker information. Please check the transcript format.");
    }
  }, [rawTranscript]);
  
  // Update preview when mappings change
  useEffect(() => {
    if (!rawTranscript) return;
    
    try {
      let updatedTranscript = rawTranscript;
      
      // Replace all speaker/company instances
      Object.entries(speakerMapping).forEach(([originalName, newName]) => {
        if (newName.trim() && newName.trim() !== originalName) {
          // Create a regex that matches the speaker in the format: "Speaker Name, Company (00:00):"
          // We need to escape special regex characters in the original name
          const escapedOriginalName = originalName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
          const pattern = new RegExp(`(^|\\n)(${escapedOriginalName})(,\\s*[^(]+\\s*\\((?:\\d{2}:\\d{2}:\\d{2}|\\d{2}:\\d{2})\\):)`, 'g');
          updatedTranscript = updatedTranscript.replace(pattern, `$1${newName.trim()}$3`);
        }
      });
      
      Object.entries(companyMapping).forEach(([originalName, newName]) => {
        if (newName.trim() && newName.trim() !== originalName) {
          // Create a regex that matches the company in the format: "Speaker Name, Company Name (00:00):"
          // We need to escape special regex characters in the original name
          const escapedOriginalName = originalName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
          const pattern = new RegExp(`(^|\\n)([^,]+,\\s*)(${escapedOriginalName})(\\s*\\((?:\\d{2}:\\d{2}:\\d{2}|\\d{2}:\\d{2})\\):)`, 'g');
          updatedTranscript = updatedTranscript.replace(pattern, `$1$2${newName.trim()}$4`);
        }
      });
      
      setPreviewTranscript(updatedTranscript);
      
      // Notify parent component of mapping changes
      onSpeakerMappingChange({
        speakerMapping,
        companyMapping
      });
    } catch (error) {
      console.error("Error updating transcript preview:", error);
      // Could set an error state here to notify the user
    }
  }, [speakerMapping, companyMapping, rawTranscript]);
  
  const handleSpeakerChange = (originalName, value) => {
    setSpeakerMapping(prev => ({
      ...prev,
      [originalName]: value
    }));
  };
  
  const handleCompanyChange = (originalName, value) => {
    setCompanyMapping(prev => ({
      ...prev,
      [originalName]: value
    }));
  };
  
  const handleApplyChanges = () => {
    try {
      onTranscriptUpdate(previewTranscript);
    } catch (error) {
      console.error("Error applying transcript changes:", error);
      // Could display an error message to the user
      // setError("Failed to apply changes to transcript.");
    }
  };
  
  return (
    <div className="speaker-editor">
      <div className="speaker-mapping-section">
        <h3>Edit Speakers and Companies</h3>
        <p className="instruction">Replace generic names with real names before processing the transcript.</p>
        
        <div className="mapping-container">
          <div className="mapping-column">
            <h4>Speakers</h4>
            {Object.entries(speakerMapping).map(([originalName, newName]) => (
              <div key={`speaker-${originalName}`} className="mapping-item">
                <label>{originalName}:</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => handleSpeakerChange(originalName, e.target.value)}
                  placeholder="Edit speaker name"
                />
              </div>
            ))}
          </div>
          
          <div className="mapping-column">
            <h4>Companies</h4>
            {Object.entries(companyMapping).map(([originalName, newName]) => (
              <div key={`company-${originalName}`} className="mapping-item">
                <label>{originalName}:</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => handleCompanyChange(originalName, e.target.value)}
                  placeholder="Edit company name"
                />
              </div>
            ))}
          </div>
        </div>
        
        <button 
          className="apply-button"
          onClick={handleApplyChanges}
          disabled={Object.entries(speakerMapping).every(([original, updated]) => !updated.trim() || updated.trim() === original) && 
                   Object.entries(companyMapping).every(([original, updated]) => !updated.trim() || updated.trim() === original)}
        >
          Save Speaker Name Changes
        </button>
      </div>
      
      <div className="preview-section">
        <h4>Preview</h4>
        <div className="transcript-preview">
          {previewTranscript.split('\n').map((line, i) => (
            <div key={i} className="preview-line">
              {line}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default SpeakerEditor;
