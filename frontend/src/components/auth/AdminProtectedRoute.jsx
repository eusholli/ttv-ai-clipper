import { useUser } from "@clerk/clerk-react";
import { Navigate } from "react-router-dom";

const AdminProtectedRoute = ({ children }) => {
  const { user, isLoaded } = useUser();
  
  if (!isLoaded) return null;
  
  // Check if user has admin role
  const isAdmin = user?.publicMetadata?.role === "admin";
  
  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }
  
  return children;
};

export default AdminProtectedRoute;
