import { useState } from 'react';
import { loadStripe } from '@stripe/stripe-js';
import { useUser, useAuth } from "@clerk/clerk-react";
import { useNavigate } from "react-router-dom";
import axios from 'axios';
import './Pricing.css';

const BACKEND_HOST = import.meta.env.VITE_BACKEND_HOST;

const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLIC_KEY);

export default function Pricing() {
  const [isAnnual, setIsAnnual] = useState(false);
  const { user } = useUser();
  const { signOut, getToken } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const plans = {
    monthly: {
      price: 1500,
      priceDisplay: '$1,500',
      period: '/month',
      savings: null,
      priceId: import.meta.env.VITE_STRIPE_MONTHLY_PRICE_ID
    },
    annual: {
      price: 10000,
      priceDisplay: '$10,000',
      period: '/year',
      savings: '$8,000',
      priceId: import.meta.env.VITE_STRIPE_ANNUAL_PRICE_ID
    }
  };

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

  const handleCheckout = async (priceId) => {
    if (!user) return;
    
    try {
      setLoading(true);
      setError(null);
      
      const token = await getToken();
      const currentStripeCustomerId = user.unsafeMetadata?.stripeCustomerId;
      
      const response = await axios.post(`${BACKEND_HOST}/api/create-checkout-session`, 
        {
          priceId: priceId,
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

  return (
    <div className="pricing-container">
      <div className="pricing-header">
        <h1>Choose Your Plan</h1>
        <p className="subtitle">Get unlimited access to Telecom TV's AI-powered video clips</p>
        
        <div className="toggle-container">
          <span className={!isAnnual ? 'active' : ''}>Monthly</span>
          <label className="switch">
            <input
              type="checkbox"
              checked={isAnnual}
              onChange={() => setIsAnnual(!isAnnual)}
            />
            <span className="slider"></span>
          </label>
          <span className={isAnnual ? 'active' : ''}>
            Annual <span className="save-badge">Save 44%</span>
          </span>
        </div>
      </div>

      <div className="pricing-cards">
        <div className={`pricing-card ${isAnnual ? 'recommended' : ''}`}>
          <div className="card-header">
            {isAnnual && <div className="recommended-badge">BEST VALUE</div>}
            <h2>{isAnnual ? 'Annual' : 'Monthly'} Plan</h2>
            <div className="price">
              <span className="amount">
                {isAnnual ? plans.annual.priceDisplay : plans.monthly.priceDisplay}
              </span>
              <span className="period">
                {isAnnual ? plans.annual.period : plans.monthly.period}
              </span>
            </div>
            {isAnnual && (
              <div className="savings">
                Save {plans.annual.savings} per year
              </div>
            )}
          </div>

          <div className="features">
            <ul>
              <li>✓ Unlimited Video Clip Downloads</li>
              <li>✓ Advanced Search & Filtering</li>
              <li>✓ High-Quality Video Exports</li>
              <li>✓ Custom Clip Lengths</li>
              <li>✓ Priority Support</li>
            </ul>
          </div>

          <button
            onClick={() => handleCheckout(isAnnual ? plans.annual.priceId : plans.monthly.priceId)}
            className="checkout-button"
            disabled={loading}
          >
            {loading ? 'Processing...' : 'Get Started Now'}
          </button>

          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

          <div className="guarantee">
            <span>🔒 30-day money-back guarantee</span>
          </div>
        </div>
      </div>

      <div className="social-proof">
        <div className="testimonials">
          <h3>Trusted by Industry Leaders</h3>
          <div className="testimonial">
            "This platform has revolutionized how we access and share telecom industry insights."
            <br />
            <span className="author">- Sarah M., Research Director</span>
          </div>
        </div>
        
        <div className="trust-badges">
          <span>🔒 Secure payments</span>
          <span>⭐ 4.9/5 Customer Rating</span>
          <span>🏆 Industry Leading Support</span>
        </div>
      </div>

      <div className="faq">
        <h3>Frequently Asked Questions</h3>
        <div className="faq-item">
          <h4>What's included in my subscription?</h4>
          <p>Your subscription includes unlimited access to our AI-powered video clip search and download functionality, along with all premium features and priority support.</p>
        </div>
        <div className="faq-item">
          <h4>Can I cancel my subscription?</h4>
          <p>Yes, you can cancel your subscription at any time. If you cancel within 30 days, we'll provide a full refund.</p>
        </div>
        <div className="faq-item">
          <h4>What payment methods do you accept?</h4>
          <p>We accept all major credit cards including Visa, Mastercard, American Express, and Discover.</p>
        </div>
      </div>

      {user && (
        <div className="delete-account-section">
          <button 
            onClick={handleDeleteAccount}
            className="delete-account-button"
          >
            Delete Account
          </button>
        </div>
      )}

      <style>{`
        .delete-account-section {
          margin-top: 40px;
          text-align: center;
        }

        .delete-account-button {
          background-color: #ff4444;
          color: white;
          padding: 10px 20px;
          border: none;
          border-radius: 4px;
          cursor: pointer;
          font-size: 16px;
          width: 200px;
        }

        .delete-account-button:hover {
          background-color: #ff0000;
        }

        .error-message {
          color: #ff0000;
          margin: 10px 0;
          text-align: center;
        }

        .checkout-button:disabled {
          background-color: #cccccc;
          cursor: not-allowed;
        }
      `}</style>
    </div>
  );
}
