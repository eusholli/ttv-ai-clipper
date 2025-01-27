import { useState } from 'react';
import { useUser } from "@clerk/clerk-react";
import { createJob } from '../api';
import ButtonWithStatus from './ButtonWithStatus';

const JobForm = ({ onJobCreated, setError, getToken }) => {
  const { user } = useUser();
  const [urls, setUrls] = useState('');
  const [loadingState, setLoadingState] = useState({ loading: false, message: '' });
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [autoApprove, setAutoApprove] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoadingState({ loading: true, message: 'Initiating ingest...' });
    setError(null);

    try {
      const newJob = await createJob(urls, user.primaryEmailAddress.emailAddress, getToken, autoApprove);
      setLoadingState({ loading: true, message: 'Starting job...' });
      onJobCreated(newJob);
      
      // Show success message briefly before resetting
      setLoadingState({ loading: true, message: 'Job created successfully!' });
      setTimeout(() => {
        setLoadingState({ loading: false, message: '' });
        // Clear form
        setUrls('');
      }, 1500);
    } catch (err) {
      setError(err.message);
      setLoadingState({ loading: false, message: '' });
    }
  };

  return (
    <form onSubmit={handleSubmit} className="ingest-form">
      <div className="form-group">
        <label htmlFor="urls">URLs to Ingest (one per line):</label>
        <textarea
          id="urls"
          value={urls}
          onChange={(e) => setUrls(e.target.value)}
          required
          placeholder="https://telecomtv.com/video-page-1&#10;https://telecomtv.com/video-page-2"
          rows={5}
          style={{ width: '100%', fontFamily: 'monospace' }}
        />
      </div>

      <div className="form-group">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={autoApprove}
            onChange={(e) => setAutoApprove(e.target.checked)}
          />
          Auto approve transcript if possible
        </label>
      </div>

      <div className="form-group">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={rightsConfirmed}
            onChange={(e) => setRightsConfirmed(e.target.checked)}
          />
          I confirm I have all necessary rights and permissions to use these videos
        </label>
      </div>

      <ButtonWithStatus
        type="submit"
        className="primary"
        disabled={loadingState.loading || !rightsConfirmed}
        isLoading={loadingState.loading}
        loadingText={loadingState.message}
      >
        Start Ingest
      </ButtonWithStatus>
    </form>
  );
};

export default JobForm;
