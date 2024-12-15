import { useAuth, useUser } from "@clerk/clerk-react";
import { Link, useNavigate } from "react-router-dom";

const Navigation = () => {
  const { isLoaded, isSignedIn, signOut } = useAuth();
  const { user } = useUser();
  const navigate = useNavigate();

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

  return (
    <nav className="auth-nav">
      <div className="nav-left">
        <Link to="/" className="nav-logo">Telecom TV</Link>
      </div>
      <div className="nav-right">
        {isSignedIn ? (
          <>
            <span className="welcome-text">Welcome, {user?.firstName}!</span>
            <Link to="/user-profile" className="nav-link">Profile</Link>
            <button 
              onClick={handleSignOut} 
              className="nav-button"
            >
              Sign Out
            </button>
          </>
        ) : (
          <>
            <Link to="/sign-in" className="nav-link">Sign In</Link>
            <Link to="/sign-up" className="nav-button">Sign Up</Link>
          </>
        )}
      </div>
    </nav>
  );
};

export default Navigation;
