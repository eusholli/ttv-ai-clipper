import { useAuth, useUser } from "@clerk/clerk-react";
import { Link, useNavigate } from "react-router-dom";
import { useState } from "react";

const Navigation = () => {
  const { isLoaded, isSignedIn, signOut } = useAuth();
  const { user } = useUser();
  const navigate = useNavigate();
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  if (!isLoaded) {
    return <div className="nav-loading">Loading...</div>;
  }

  const handleSignOut = async () => {
    try {
      await signOut();
      navigate("/sign-in");
    } catch (error) {
      console.error("Error signing out:", error);
    }
  };

  const toggleMenu = () => {
    setIsMenuOpen(!isMenuOpen);
  };

  return (
    <nav className="auth-nav">
      <div className="nav-left">
        <Link to="/" className="nav-logo">Telecom TV</Link>
      </div>
      
      <button className="hamburger-menu" onClick={toggleMenu} aria-label="Toggle menu">
        <span className="hamburger-line"></span>
        <span className="hamburger-line"></span>
        <span className="hamburger-line"></span>
      </button>

      <div className={`nav-right ${isMenuOpen ? 'nav-right-open' : ''}`}>
        {isSignedIn ? (
          <>
            <span className="welcome-text">Welcome, {user?.firstName}!</span>
            <Link to="/user-profile" className="nav-link" onClick={() => setIsMenuOpen(false)}>
              My Subscription
            </Link>
            <Link to="/admin/ingest" className="nav-link" onClick={() => setIsMenuOpen(false)}>
              Admin Ingest
            </Link>
            <button 
              onClick={() => {
                handleSignOut();
                setIsMenuOpen(false);
              }} 
              className="nav-button"
            >
              Sign Out
            </button>
          </>
        ) : (
          <>
            <Link to="/sign-in" className="nav-link" onClick={() => setIsMenuOpen(false)}>
              Sign In
            </Link>
          </>
        )}
      </div>
    </nav>
  );
};

export default Navigation;
