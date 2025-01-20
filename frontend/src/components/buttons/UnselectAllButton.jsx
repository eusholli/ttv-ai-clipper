import React, { useState, useEffect } from 'react';
import { useAuth, useUser } from '@clerk/clerk-react';
import axios from 'axios';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL;

const UnselectAllButton = ({ selectedClips, setSelectedClips }) => {
  const { isSignedIn, getToken } = useAuth();
  const { user } = useUser();
  const [hasActiveSubscription, setHasActiveSubscription] = useState(false);

  useEffect(() => {
    const checkSubscription = async () => {
      if (!isSignedIn || !user?.unsafeMetadata?.stripeCustomerId) {
        setHasActiveSubscription(false);
        return;
      }

      try {
        const token = await getToken();
        const response = await axios.get(
          `${BACKEND_URL}/api/subscription-status?customer_id=${user.unsafeMetadata.stripeCustomerId}`,
          { headers: { Authorization: `Bearer ${token}` }}
        );
        setHasActiveSubscription(response.data.status === 'active');
      } catch (err) {
        console.error('Error checking subscription:', err);
        setHasActiveSubscription(false);
      }
    };

    checkSubscription();
  }, [isSignedIn, user]);

  return (
    <button 
      className={`unselect-all-button ${selectedClips.length === 0 || !hasActiveSubscription ? 'inactive' : ''}`}
      onClick={() => setSelectedClips([])}
      disabled={selectedClips.length === 0 || !hasActiveSubscription}
    >
      Unselect all
    </button>
  );
};

export default UnselectAllButton;
