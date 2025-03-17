import { useState } from 'react';
import { updateContent, validateContent } from '../api';
import ValidationResultModal from './ValidationResultModal';
import SpeakerEditor from './SpeakerEditor';

const ContentEditor = ({ jobId, jobDetails, onClose, onUpdate, getToken, setError }) => {
  const [activeTab, setActiveTab] = useState('metadata');
  const [validationResult, setValidationResult] = useState(null);
  const [showValidationModal, setShowValidationModal] = useState(false);
  const [speakerMapping, setSpeakerMapping] = useState(null);
  const [content, setContent] = useState({
    metadata: {
      ...jobDetails?.metadata
    },
    raw_transcript: jobDetails?.raw_transcript || ''
  });

  if (!jobDetails?.metadata) return null;

  const handleMetadataChange = (field, value) => {
    setContent(prev => ({
      ...prev,
      metadata: {
        ...prev.metadata,
        [field]: value
      }
    }));
  };

  const handleTranscriptUpdate = (updatedTranscript) => {
    setContent(prev => ({
      ...prev,
      raw_transcript: updatedTranscript
    }));
  };

  const handleSpeakerMappingChange = (mapping) => {
    setSpeakerMapping(mapping);
  };

  const handleSave = async () => {
        try {
          const result = await updateContent(jobId, content, getToken);
          if (result.parsing_status) {
            try {
              // Update job details with new parsing status before closing
              await onUpdate(jobId);
            } catch (updateErr) {
              console.error("Error updating job details:", updateErr);
              setError(`Changes were saved but there was an error refreshing job details: ${updateErr.message}`);
              return; // Don't close the editor if we can't update job details
            }
          }
          onClose();
        } catch (err) {
          console.error("Error saving content:", err);
          setError(`Failed to save changes: ${err.message}`);
        }
  };

  return (
    <div className="content-editor">
      <div className="editor-header">
        <h3>Edit Content</h3>
        <div className="tab-buttons">
          <button 
            className={`tab-button ${activeTab === 'metadata' ? 'active' : ''}`}
            onClick={() => setActiveTab('metadata')}
          >
            Metadata
          </button>
          <button 
            className={`tab-button ${activeTab === 'speakers' ? 'active' : ''}`}
            onClick={() => setActiveTab('speakers')}
          >
            Speakers
          </button>
          <button 
            className={`tab-button ${activeTab === 'transcript' ? 'active' : ''}`}
            onClick={() => setActiveTab('transcript')}
          >
            Transcript
          </button>
        </div>
      </div>

      <div className="editor-content">
        {activeTab === 'metadata' && (
          <div className="metadata-section">
            <div className="form-group">
              <label>Title:</label>
              <input
                value={content.metadata.title || ''}
                onChange={(e) => handleMetadataChange('title', e.target.value)}
                placeholder="Enter title"
              />
            </div>
            <div className="form-group">
              <label>Date:</label>
              <input
                value={content.metadata.date || ''}
                onChange={(e) => handleMetadataChange('date', e.target.value)}
                placeholder="Enter date"
              />
            </div>
            <div className="form-group">
              <label>YouTube ID:</label>
              <input
                value={content.metadata.youtube_id || ''}
                onChange={(e) => handleMetadataChange('youtube_id', e.target.value)}
                placeholder="Enter YouTube ID"
              />
            </div>
          </div>
        )}

        {activeTab === 'speakers' && (
          <SpeakerEditor
            rawTranscript={content.raw_transcript}
            onTranscriptUpdate={handleTranscriptUpdate}
            onSpeakerMappingChange={handleSpeakerMappingChange}
          />
        )}

        {activeTab === 'transcript' && (
          <div className="transcript-section">
            <div className="raw-transcript">
              <h4>Raw Transcript</h4>
              <textarea
                value={content.raw_transcript}
                onChange={(e) => setContent(prev => ({
                  ...prev,
                  raw_transcript: e.target.value
                }))}
                rows={10}
                style={{ width: '100%', fontFamily: 'monospace' }}
                placeholder="Enter raw transcript text"
              />
            </div>
          </div>
        )}
      </div>

      <div className="editor-footer">
        <div className="button-group">
          <button onClick={async () => {
            try {
              const result = await validateContent(jobId, content, getToken);
              setValidationResult(result);
              setShowValidationModal(true);
            } catch (err) {
              console.error("Error validating content:", err);
              setError(`Failed to validate content: ${err.message}`);
            }
          }} className="validate-button">
            Validate Content
          </button>
          <button onClick={handleSave} className="save-button">Save All Changes</button>
          <button onClick={onClose} className="cancel-button">Cancel</button>
        </div>
      </div>

      {showValidationModal && (
        <ValidationResultModal
          result={validationResult}
          onClose={() => setShowValidationModal(false)}
        />
      )}

      <style jsx>{`
        .raw-transcript {
          margin-bottom: 20px;
        }

        .raw-transcript h4 {
          margin: 0 0 10px 0;
          color: #333;
        }

        .content-editor {
          background: white;
          border-radius: 8px;
          box-shadow: 0 2px 4px rgba(0,0,0,0.1);
          margin: 20px 0;
          padding: 20px;
        }

        .editor-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 20px;
        }

        .tab-buttons {
          display: flex;
          gap: 10px;
        }

        .tab-button {
          padding: 8px 16px;
          border: 1px solid #ddd;
          border-radius: 4px;
          background: none;
          cursor: pointer;
        }

        .tab-button.active {
          background: #007bff;
          color: white;
          border-color: #007bff;
        }

        .editor-content {
          max-height: 600px;
          overflow-y: auto;
          padding: 20px 0;
        }

        .form-group {
          margin-bottom: 15px;
        }

        .form-group label {
          display: block;
          margin-bottom: 5px;
          font-weight: 500;
        }

        .form-group input {
          width: 100%;
          padding: 8px;
          border: 1px solid #ddd;
          border-radius: 4px;
        }

        textarea {
          width: 100%;
          padding: 8px;
          border: 1px solid #ddd;
          border-radius: 4px;
          resize: vertical;
        }

        .editor-footer {
          display: flex;
          justify-content: flex-end;
          margin-top: 20px;
          padding-top: 20px;
          border-top: 1px solid #ddd;
        }

        .button-group {
          display: flex;
          gap: 10px;
        }

        .validate-button {
          background: #17a2b8;
          color: white;
          border: none;
          padding: 8px 16px;
          border-radius: 4px;
          cursor: pointer;
        }

        .validate-button:hover {
          background: #138496;
        }

        .save-button {
          background: #28a745;
          color: white;
          border: none;
          padding: 8px 16px;
          border-radius: 4px;
          cursor: pointer;
        }

        .save-button:hover {
          background: #218838;
        }

        .cancel-button {
          background: #6c757d;
          color: white;
          border: none;
          padding: 8px 16px;
          border-radius: 4px;
          cursor: pointer;
        }

        .cancel-button:hover {
          background: #5a6268;
        }
      `}</style>
    </div>
  );
};

export default ContentEditor;
