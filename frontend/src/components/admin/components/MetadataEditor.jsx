import { updateMetadata } from '../api';

const MetadataEditor = ({ jobId, jobDetails, onClose, onUpdate, getToken, setError }) => {
  if (!jobDetails?.metadata) return null;
  const metadata = jobDetails.metadata;

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const formData = new FormData(e.target);
      await updateMetadata(jobId, {
        title: formData.get('title'),
        date: formData.get('date'),
        youtube_id: formData.get('youtube_id'),
        source: formData.get('source')
      }, getToken);
      
      await onUpdate(jobId);
      onClose();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="metadata-editor">
      <h3>Edit Metadata</h3>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>Title:</label>
          <input name="title" defaultValue={metadata.title || ''} />
        </div>
        <div className="form-group">
          <label>Date:</label>
          <input name="date" defaultValue={metadata.date || ''} />
        </div>
        <div className="form-group">
          <label>YouTube ID:</label>
          <input name="youtube_id" defaultValue={metadata.youtube_id || ''} />
        </div>
        <div className="form-group">
          <label>Source:</label>
          <input name="source" defaultValue={metadata.source || ''} />
        </div>
        <div className="button-group">
          <button type="submit">Save</button>
          <button type="button" onClick={onClose}>Cancel</button>
        </div>
      </form>
    </div>
  );
};

export default MetadataEditor;
