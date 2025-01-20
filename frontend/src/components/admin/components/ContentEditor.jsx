import { useState } from 'react';
import { updateContent, validateContent } from '../api';
import ValidationResultModal from './ValidationResultModal';

const ContentEditor = ({ jobId, jobDetails, onClose, onUpdate, getToken, setError }) => {
  const [activeTab, setActiveTab] = useState('metadata');
  const [validationResult, setValidationResult] = useState(null);
  const [showValidationModal, setShowValidationModal] = useState(false);
  const [content, setContent] = useState({
    metadata: {
      ...jobDetails?.metadata
    },
    transcript: jobDetails?.transcript || ''
  });

  if (!jobDetails?.metadata || !jobDetails?.transcript) return null;

  const parseTranscript = (text) => {
    // Split into segments by double newlines
    const segments = text.split('\n\n');
    const parsedSegments = [];

    for (const segment of segments) {
      // Match pattern: "Speaker, Company (MM:SS): Text"
      const match = segment.match(/^(.*?), (.*?)\s*\((\d+:\d+)\):\s*(.*)$/s);
      if (match) {
        const [_, speaker, company, timestamp, text] = match;
        parsedSegments.push({ speaker, company, timestamp, text });
      }
    }
    return parsedSegments;
  };

  const handleMetadataChange = (field, value) => {
    setContent(prev => ({
      ...prev,
      metadata: {
        ...prev.metadata,
        [field]: value
      }
    }));
  };

  const handleSave = async () => {
    try {
      await updateContent(jobId, content, getToken);
      await onUpdate(jobId); // Pass jobId to onUpdate
      onClose();
    } catch (err) {
      setError(err.message);
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

        {activeTab === 'transcript' && (
          <div className="transcript-section">
            <textarea
              value={content.transcript}
              onChange={(e) => setContent(prev => ({
                ...prev,
                transcript: e.target.value
              }))}
              rows={20}
              style={{ width: '100%', fontFamily: 'monospace' }}
            />
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
              setError(err.message);
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
