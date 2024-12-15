import { useUser, useAuth } from "@clerk/clerk-react";
import { useNavigate } from "react-router-dom";

const UserProfilePage = () => {
  const { user } = useUser();
  const { signOut } = useAuth();
  const navigate = useNavigate();

  if (!user) {
    return <div>Loading...</div>;
  }

  const handleDeleteAccount = async () => {
    if (window.confirm("Are you sure you want to delete your account? This action cannot be undone.")) {
      try {
        // Store a local reference to the delete function
        const deleteAccount = user.delete.bind(user);
        
        // First delete the account
        await deleteAccount();
        
        // Then sign out and navigate
        await signOut();
        navigate("/sign-up");
      } catch (error) {
        console.error("Error deleting account:", error);
        alert("Failed to delete account. Please try again.");
      }
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <h2>User Profile</h2>
        
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
        </div>

        <div className="profile-actions">
          <button 
            onClick={handleDeleteAccount}
            className="delete-account-button"
          >
            Delete Account
          </button>
        </div>
      </div>
    </div>
  );
};

export default UserProfilePage;
