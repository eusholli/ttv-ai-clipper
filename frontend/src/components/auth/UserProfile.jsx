import { useUser, useAuth } from "@clerk/clerk-react";
import { useNavigate, useLocation } from "react-router-dom";
import { loadStripe } from "@stripe/stripe-js";
import { useState, useEffect } from "react";
import axios from "axios";

// Initialize Stripe
const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLIC_KEY);
const SUBSCRIPTION_PRICE_ID = import.meta.env.VITE_STRIPE_MONTHLY_PRICE_ID;

const UserProfilePage = () => {
  const { user } = useUser();
  const { signOut, getToken } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [loading, setLoading] = useState(false);
  const [subscriptionStatus, setSubscriptionStatus] = useState(null);
  const [error, setError] = useState(null);
  const [showSuccess, setShowSuccess] = useState(false);

  const updateUserMetadata = async (stripeCustomerId) => {
    try {
      // Get current metadata
      const currentMetadata = user.unsafeMetadata || {};
      
      // Update metadata with new Stripe Customer ID while preserving other fields
      await user.update({
        unsafeMetadata: {
          ...currentMetadata,
          stripeCustomerId
        }
      });
      
      console.log("Successfully updated user metadata with Stripe Customer ID");
    } catch (err) {
      console.error("Error updating user metadata:", err);
      throw err;
    }
  };

  const checkSubscription = async () => {
    if (!user) return;
    
    try {
      console.log("Checking subscription status...");
      const stripeCustomerId = user.unsafeMetadata?.stripeCustomerId;
      console.log("Stripe Customer ID:", stripeCustomerId);
      
      const token = await getToken();
      if (stripeCustomerId) {
        console.log("Making API call to check subscription status");
        const response = await axios.get(`/api/subscription-status?customer_id=${stripeCustomerId}`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        console.log("Subscription status response:", response.data);
        setSubscriptionStatus(response.data);
      } else {
        console.log("No Stripe Customer ID found, setting status to inactive");
        setSubscriptionStatus({ status: 'inactive' });
      }
    } catch (err) {
      console.error("Error checking subscription:", err);
      setSubscriptionStatus({ status: 'inactive' });
    }
  };

  useEffect(() => {
    if (user) {
      console.log("User loaded, current metadata:", user.unsafeMetadata);
      checkSubscription();
    }
  }, [user]);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get('success') === 'true' && user) {
      setShowSuccess(true);
      checkSubscription();
      const checkInterval = setInterval(checkSubscription, 2000);
      const maxChecks = 5;
      let checkCount = 0;

      const timer = setTimeout(() => {
        clearInterval(checkInterval);
        navigate('/user-profile', { replace: true });
        setShowSuccess(false);
      }, 10000);

      return () => {
        clearTimeout(timer);
        clearInterval(checkInterval);
      };
    }
  }, [location, navigate, user]);

  const handleSubscribe = async () => {
    if (!user) return;
    
    try {
      setLoading(true);
      setError(null);
      
      const token = await getToken();
      const currentStripeCustomerId = user.unsafeMetadata?.stripeCustomerId;
      
      const response = await axios.post("/api/create-checkout-session", 
        {
          priceId: SUBSCRIPTION_PRICE_ID,
          customerId: currentStripeCustomerId
        },
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );

      if (!currentStripeCustomerId && response.data.customerId) {
        await updateUserMetadata(response.data.customerId);
      }

      window.location.href = response.data.url;

    } catch (err) {
      console.error("Subscription error:", err);
      setError(err.message || "Failed to process subscription");
      setLoading(false);
    }
  };

  const handleManageSubscription = async () => {
    if (!user) return;
    
    try {
      setLoading(true);
      setError(null);
      
      const token = await getToken();
      const stripeCustomerId = user.unsafeMetadata?.stripeCustomerId;
      
      if (!stripeCustomerId) {
        throw new Error("No Stripe Customer ID found");
      }
      
      // Changed to use query parameter instead of request body
      const response = await axios.post(
        `/api/create-portal-session?customer_id=${stripeCustomerId}`,
        {},  // Empty body since we're using query parameter
        { headers: { Authorization: `Bearer ${token}` } }
      );

      window.location.href = response.data.url;

    } catch (err) {
      console.error("Portal session error:", err);
      setError(err.message || "Failed to access subscription management");
      setLoading(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (!user) return;
    
    if (window.confirm("Are you sure you want to delete your account? This action cannot be undone.")) {
      try {
        const deleteAccount = user.delete.bind(user);
        await deleteAccount();
        await signOut();
        navigate("/sign-up");
      } catch (error) {
        console.error("Error deleting account:", error);
        alert("Failed to delete account. Please try again.");
      }
    }
  };

  if (!user) {
    return <div>Loading...</div>;
  }

  return (
    <div className="auth-container">
      <div className="auth-card">
        <h2>User Profile</h2>
        
        {showSuccess && (
          <div className="success-message">
            Subscription successful! Thank you for subscribing.
          </div>
        )}
        
        <div className="profile-info">
          <div className="profile-field">
            <label>First Name:</label>
            <span>{user.firstName}</span>
          </div>
          
          <div className="profile-field">
            <label>Last Name:</label>
            <span>{user.lastName}</span>
          </div>
          
          <div className="profile-field">
            <label>Email:</label>
            <span>{user.primaryEmailAddress?.emailAddress}</span>
          </div>

          <div className="profile-field">
            <label>Subscription Status:</label>
            <span>
              {subscriptionStatus?.status === 'active' ? (
                <>
                  Active ({subscriptionStatus.cancelAtPeriodEnd ? 'Ends' : 'Renews'}: {new Date(subscriptionStatus.currentPeriodEnd * 1000).toLocaleDateString()})
                </>
              ) : (
                'Inactive'
              )}
            </span>
          </div>
        </div>

        <div className="profile-actions">
          {subscriptionStatus?.status === 'active' ? (
            <button
              onClick={handleManageSubscription}
              disabled={loading}
              className="manage-subscription-button"
            >
              {loading ? 'Processing...' : 'Manage Subscription'}
            </button>
          ) : (
            <button
              onClick={handleSubscribe}
              disabled={loading}
              className="subscribe-button"
            >
              {loading ? 'Processing...' : 'Subscribe ($1500/month)'}
            </button>
          )}

          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

          {subscriptionStatus?.status !== 'active' && (
            <button 
              onClick={handleDeleteAccount}
              className="delete-account-button"
            >
              Delete Account
            </button>
          )}
        </div>
      </div>

      <style>{`
        .success-message {
          background-color: #d4edda;
          color: #155724;
          padding: 15px;
          margin-bottom: 20px;
          border: 1px solid #c3e6cb;
          border-radius: 4px;
          text-align: center;
        }

        .subscribe-button,
        .manage-subscription-button {
          background-color: #4CAF50;
          color: white;
          padding: 10px 20px;
          border: none;
          border-radius: 4px;
          cursor: pointer;
          font-size: 16px;
          margin-bottom: 10px;
          width: 100%;
        }

        .manage-subscription-button {
          background-color: #2196F3;
        }

        .subscribe-button:disabled,
        .manage-subscription-button:disabled {
          background-color: #cccccc;
          cursor: not-allowed;
        }

        .error-message {
          color: #ff0000;
          margin: 10px 0;
          text-align: center;
        }

        .profile-field {
          margin-bottom: 15px;
        }

        .profile-field label {
          font-weight: bold;
          margin-right: 10px;
        }

        .profile-actions {
          margin-top: 20px;
        }

        .delete-account-button {
          background-color: #ff4444;
          color: white;
          padding: 10px 20px;
          border: none;
          border-radius: 4px;
          cursor: pointer;
          font-size: 16px;
          width: 100%;
        }
      `}</style>
    </div>
  );
};

export default UserProfilePage;
