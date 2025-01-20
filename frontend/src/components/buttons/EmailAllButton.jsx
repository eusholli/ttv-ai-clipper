import React, { useState } from 'react';
import { useAuth, useUser } from '@clerk/clerk-react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL;

const EmailAllButton = ({ selectedClips }) => {
  const { isSignedIn, getToken } = useAuth();
  const { user } = useUser();
  const navigate = useNavigate();
  const [sending, setSending] = useState(false);

  const handleEmailAll = async () => {
    if (!isSignedIn) {
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
      const token = await getToken();
      const stripeCustomerId = user?.unsafeMetadata?.stripeCustomerId;
      
      if (!stripeCustomerId) {
        navigate('/user-profile');
        return;
      }

      const response = await axios.get(`${BACKEND_URL}/api/subscription-status?customer_id=${stripeCustomerId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (response.data.status !== 'active') {
        navigate('/user-profile');
        return;
      }

      setSending(true);
      
      const emailResponse = await axios.post(
        `${BACKEND_URL}/api/email-clips`,
        { segment_hashes: selectedClips },
        { headers: { Authorization: `Bearer ${token}` }}
      );
      if (emailResponse.data.status === 'success') {
        alert('Email sent successfully!');
      }
    } catch (err) {
      console.error('Error emailing clips:', err);
      if (err.response?.status === 403) {
        navigate('/pricing');
      } else {
        alert(`Failed to email clips:\n${err.message}`);
      }
    } finally {
      setSending(false);
    }
  };

  return (
    <button 
      className={`email-all-button ${selectedClips.length === 0 ? 'inactive' : ''}`}
      onClick={handleEmailAll}
      disabled={sending || selectedClips.length === 0}
    >
      {sending ? 'Sending...' : `Email ${selectedClips.length} selected clip${selectedClips.length !== 1 ? 's' : ''}`}
    </button>
  );
};

export default EmailAllButton;
