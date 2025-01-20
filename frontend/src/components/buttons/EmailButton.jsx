import React from 'react';
import { useAuth, useUser } from '@clerk/clerk-react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { EmailIcon } from '../icons';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL;

const EmailButton = ({ result, emailing, setEmailing }) => {
  const { isSignedIn, getToken } = useAuth();
  const { user } = useUser();
  const navigate = useNavigate();

  const handleEmail = async () => {
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
      // Check subscription status first
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

      setEmailing({ ...emailing, [result.segment_hash]: true });
      
      const emailResponse = await axios.post(
        `${BACKEND_URL}/api/email-clips`,
        { segment_hashes: [result.segment_hash] },
        { headers: { Authorization: `Bearer ${token}` }}
      );

      if (emailResponse.data.status === 'success') {
        alert('Email sent successfully!');
      }
    } catch (err) {
      console.error('Error emailing clip:', err);
      if (err.response?.status === 403) {
        navigate('/pricing');
      } else {
        alert(`Failed to email clip:\n${err.message}`);
      }
    } finally {
      setEmailing({ ...emailing, [result.segment_hash]: false });
    }
  };

  return (
    <button
      className="email-button"
      onClick={handleEmail}
      disabled={emailing[result.segment_hash]}
    >
      <EmailIcon />
      {emailing[result.segment_hash] ? 'Sending...' : 
       !isSignedIn ? 'Subscribe to Email' : 'Email clip to me'}
    </button>
  );
};

export default EmailButton;
