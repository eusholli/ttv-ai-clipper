const LogViewer = ({ logContent, onClose }) => {
  return (
    <div className="log-viewer">
      <h2>Job Log</h2>
      <button onClick={onClose} className="close-button">Close</button>
      <pre className="log-content">{logContent}</pre>
    </div>
  );
};

export default LogViewer;
