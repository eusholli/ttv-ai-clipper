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
          <pre>{JSON.stringify(result, null, 2)}</pre>
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
