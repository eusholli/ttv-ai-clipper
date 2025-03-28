import { useState, useEffect } from 'react'; // Added useEffect
import { useUser } from "@clerk/clerk-react";
import { createJob } from '../api';
import ButtonWithStatus from './ButtonWithStatus';

// Basic YouTube URL validation regex
const YOUTUBE_URL_REGEX = /^(https?:\/\/)?(www\.)?(youtube\.com\/watch\?v=|youtu\.be\/)[\w-]{11}.*$/;

const isValidYoutubeUrl = (url) => {
  return YOUTUBE_URL_REGEX.test(url.trim());
};

const JobForm = ({ onJobCreated, setError, getToken }) => {
  const { user } = useUser();
  const [urls, setUrls] = useState('');
  const [loadingState, setLoadingState] = useState({ loading: false, message: '' });
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [autoApprove, setAutoApprove] = useState(false);
  const [urlError, setUrlError] = useState(''); // Added state for URL validation error

  // Validate URLs whenever the urls state changes
  useEffect(() => {
    const urlList = urls.split('\n').filter(url => url.trim() !== '');
    if (urlList.length === 0) {
      setUrlError(''); // No error if empty
      return;
    }
    const invalidUrls = urlList.filter(url => !isValidYoutubeUrl(url));
    if (invalidUrls.length > 0) {
      setUrlError(`Invalid YouTube URL(s) detected: ${invalidUrls.join(', ')}. Please enter valid YouTube video URLs only.`);
    } else {
      setUrlError(''); // Clear error if all are valid
    }
  }, [urls]);


  const handleSubmit = async (e) => {
    e.preventDefault();

    // --- Added URL Validation Check ---
    if (urlError) {
      setError(urlError); // Use existing setError prop
      return; // Prevent submission if there's an error
    }
    const urlList = urls.split('\n').filter(url => url.trim() !== '');
    if (urlList.length === 0) {
        setError("Please enter at least one YouTube URL.");
        return;
    }
    // --- End URL Validation Check ---

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
          placeholder="https://www.youtube.com/watch?v=xxxxxxxxxxx&#10;https://youtu.be/yyyyyyyyyyy" // Updated placeholder
          rows={5}
          style={{ width: '100%', fontFamily: 'monospace' }}
          aria-invalid={!!urlError} // Indicate invalid state for accessibility
          aria-describedby="url-error"
        />
        {/* Display URL validation error */}
        {urlError && <p id="url-error" style={{ color: 'red', marginTop: '5px' }}>{urlError}</p>}
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
        disabled={loadingState.loading || !rightsConfirmed || !!urlError || urls.trim() === ''} // Disable if error, loading, rights not confirmed, or empty
        isLoading={loadingState.loading}
        loadingText={loadingState.message}
      >
        Start Ingest
      </ButtonWithStatus>
    </form>
  );
};

export default JobForm;
