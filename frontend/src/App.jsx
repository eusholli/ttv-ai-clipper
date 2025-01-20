import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ClerkProvider, SignedIn } from '@clerk/clerk-react';
import './styles.css';

// Components
import MainContent from './components/MainContent';
import SignInPage from './components/auth/SignIn';
import SignUpPage from './components/auth/SignUp';
import UserProfilePage from './components/auth/UserProfile';
import Navigation from './components/auth/Navigation';
import Pricing from './components/pricing/Pricing';
import IngestManager from './components/admin/IngestManager';

// Protected Route Component
const ProtectedRoute = ({ children }) => {
  return (
    <SignedIn>
      {children}
    </SignedIn>
  );
};

function App() {
  console.log('import.meta.env:', import.meta.env);
  const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

  if (!publishableKey) {
    console.error("Missing needed keys. Please check your environment variables.");
    return (
      <div style={{ 
        padding: '20px', 
        textAlign: 'center', 
        color: '#721c24',
        backgroundColor: '#f8d7da',
        border: '1px solid #f5c6cb',
        borderRadius: '4px',
        margin: '20px'
      }}>
        <h2>Configuration Error</h2>
        <p>The application is missing required configuration. Please contact the administrator.</p>
      </div>
    );
  }

  return (
    <ClerkProvider 
      publishableKey={publishableKey}
      routing="path"
    >
      <Router>
        <div className="App">
          <Navigation />
          <Routes>
            <Route path="/" element={<MainContent />} />
            <Route path="/sign-in/*" element={<SignInPage />} />
            <Route path="/sign-up/*" element={<SignUpPage />} />
            <Route path="/pricing" element={<Pricing />} />
            <Route 
              path="/user-profile/*" 
              element={
                <ProtectedRoute>
                  <UserProfilePage />
                </ProtectedRoute>
              } 
            />
            {/* Add redirect from /profile to /user-profile */}
            <Route 
              path="/profile" 
              element={
                <ProtectedRoute>
                  <Navigate to="/user-profile" replace />
                </ProtectedRoute>
              } 
            />
            <Route
              path="/admin/ingest"
              element={
                <ProtectedRoute>
                  <IngestManager />
                </ProtectedRoute>
              }
            />
          </Routes>
        </div>
      </Router>
    </ClerkProvider>
  );
}

export default App;
