import React from 'react';

const ValidationResultModal = ({ result, onClose }) => {
  return (
    <div className="validation-modal">
      <div className="modal-content">
        <div className="modal-header">
          <h3>Validation Result</h3>
          <button onClick={onClose} className="close-button">&times;</button>
        </div>
        <div className="modal-body">
          {result.success ? (
            <div className="success-message">
              <div className="success-header">
                <span className="success-icon">✓</span>
                <h4>Validation Successful</h4>
              </div>
              <div className="metadata-section">
                <h5>Metadata</h5>
                <pre>{JSON.stringify(result.data.metadata, null, 2)}</pre>
              </div>
              <div className="segments-section">
                <h5>Parsed Segments ({result.data.transcript.length})</h5>
                <pre>{JSON.stringify(result.data.transcript, null, 2)}</pre>
              </div>
            </div>
          ) : (
            <div className="error-message">
              <div className="error-header">
                <span className="error-icon">✕</span>
                <h4>Validation Failed</h4>
              </div>
              <p className="error-text">{result.error}</p>
            </div>
          )}
        </div>
        <div className="modal-footer">
          <button onClick={onClose} className="close-button-bottom">Close</button>
        </div>
      </div>

      <style jsx>{`
        .validation-modal {
          position: fixed;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          background: rgba(0, 0, 0, 0.5);
          display: flex;
          justify-content: center;
          align-items: center;
          z-index: 1000;
        }

        .modal-content {
          background: white;
          border-radius: 8px;
          width: 80%;
          max-width: 800px;
          height: 80vh;
          min-height: 400px;
          overflow: hidden;
          display: flex;
          flex-direction: column;
          box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }

        .modal-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 15px 20px;
          border-bottom: 1px solid #eee;
        }

        .modal-header h3 {
          margin: 0;
        }

        .close-button {
          background: none;
          border: none;
          font-size: 24px;
          cursor: pointer;
          padding: 0;
          color: #666;
        }

        .close-button:hover {
          color: #333;
        }

        .modal-body {
          padding: 20px;
          overflow-y: auto;
          flex: 1;
        }

        .success-message, .error-message {
          padding: 15px;
          border-radius: 4px;
        }

        .success-message {
          background-color: #f0fff4;
          border: 1px solid #68d391;
        }

        .error-message {
          background-color: #fff5f5;
          border: 1px solid #fc8181;
        }

        .success-header, .error-header {
          display: flex;
          align-items: center;
          margin-bottom: 15px;
        }

        .success-icon {
          color: #38a169;
          font-size: 24px;
          margin-right: 10px;
        }

        .error-icon {
          color: #e53e3e;
          font-size: 24px;
          margin-right: 10px;
        }

        .metadata-section, .segments-section {
          margin-top: 20px;
          background: #f7fafc;
          padding: 15px;
          border-radius: 4px;
        }

        .error-text {
          color: #e53e3e;
          font-weight: 500;
          margin: 0;
        }

        .more-segments {
          color: #718096;
          font-style: italic;
          margin-top: 10px;
        }

        h4 {
          margin: 0;
          color: #2d3748;
        }

        h5 {
          margin: 0 0 10px 0;
          color: #4a5568;
          font-size: 1.1em;
        }

        pre {
          background: #fff;
          padding: 10px;
          border-radius: 4px;
          border: 1px solid #e2e8f0;
          font-size: 0.9em;
          overflow-x: auto;
        }

        .modal-footer {
          padding: 15px 20px;
          border-top: 1px solid #eee;
          display: flex;
          justify-content: flex-end;
        }

        .close-button-bottom {
          background: #6c757d;
          color: white;
          border: none;
          padding: 8px 16px;
          border-radius: 4px;
          cursor: pointer;
        }

        .close-button-bottom:hover {
          background: #5a6268;
        }

        pre {
          margin: 0;
          white-space: pre-wrap;
          word-wrap: break-word;
          font-family: monospace;
          font-size: 14px;
          line-height: 1.5;
          background: #f5f5f5;
          padding: 15px;
          border-radius: 4px;
        }
      `}</style>
    </div>
  );
};

export default ValidationResultModal;
