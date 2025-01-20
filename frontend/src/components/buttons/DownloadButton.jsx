import React from 'react';
import { useAuth, useUser } from '@clerk/clerk-react';
import { useNavigate } from 'react-router-dom';
import { DownloadIcon } from '../icons';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL;

const DownloadButton = ({ result, downloading, setDownloading }) => {
  const { isSignedIn, getToken } = useAuth();
  const { user } = useUser();
  const navigate = useNavigate();

  const handleDownload = async () => {
    if (!isSignedIn) {
      // Save search state and auth flag to sessionStorage before redirecting
      sessionStorage.setItem('searchState', JSON.stringify({
        searchQuery: window.searchQuery,
        selectedFilters: window.selectedFilters,
        numResults: window.numResults
      }));
      sessionStorage.setItem('fromAuth', 'true');
      navigate('/sign-in');
      return;
    }

    try {
      // Check subscription status first
      const token = await getToken();
      const stripeCustomerId = user?.unsafeMetadata?.stripeCustomerId;
      
      if (!stripeCustomerId) {
        navigate('/user-profile');
        return;
      }

      const response = await fetch(`${BACKEND_URL}/api/subscription-status?customer_id=${stripeCustomerId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (response.status !== 200) {
        navigate('/user-profile');
        return;
      }

      setDownloading({ ...downloading, [result.segment_hash]: true });
      
      const downloadResponse = await fetch(`${BACKEND_URL}/api/download/${result.segment_hash}`);
      if (!downloadResponse.ok) {
        const errorText = await downloadResponse.text();
        throw new Error(`Status: ${downloadResponse.status}\nMessage: ${errorText}`);
      }
      
      const blob = await downloadResponse.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `clip-${result.segment_hash}.mp4`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Error downloading clip:', err);
      if (err.response?.status === 403) {
        navigate('/pricing');
      } else {
        alert(`Failed to download clip:\n${err.message}`);
      }
    } finally {
      setDownloading({ ...downloading, [result.segment_hash]: false });
    }
  };

  return (
    <button
      className="download-button"
      onClick={handleDownload}
      disabled={downloading[result.segment_hash]}
    >
      <DownloadIcon />
      {downloading[result.segment_hash] ? 'Downloading...' : 
       !isSignedIn ? 'Subscribe to Download' : 'Download Clip'}
    </button>
  );
};

export default DownloadButton;
