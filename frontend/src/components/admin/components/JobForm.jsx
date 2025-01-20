import { useState } from 'react';
import { createJob } from '../api';

const JobForm = ({ onJobCreated, setError, getToken }) => {
  const [url, setUrl] = useState('');
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const newJob = await createJob(url, email, getToken);
      onJobCreated(newJob);
      
      // Clear form
      setUrl('');
      setEmail('');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="ingest-form">
      <div className="form-group">
        <label htmlFor="url">URL to Ingest:</label>
        <input
          type="url"
          id="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
          placeholder="https://example.com/transcript"
        />
      </div>

      <div className="form-group">
        <label htmlFor="email">Notification Email:</label>
        <input
          type="email"
          id="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          placeholder="user@example.com"
        />
      </div>

      <button type="submit" disabled={loading}>
        {loading ? 'Creating Job...' : 'Start Ingest'}
      </button>
    </form>
  );
};

export default JobForm;
