import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ children }) {
  const { status, sessionExpired } = useAuth();
  const location = useLocation();

  if (status === "checking") {
    return (
      <div className="boot" role="status" aria-live="polite">
        <span className="spinner spinner-lg" />
        <span className="sr-only">Loading</span>
      </div>
    );
  }
  if (status === "guest") {
    // Remember where they were going so login can bring them straight back.
    return <Navigate to="/login" replace state={{ from: location.pathname, expired: sessionExpired }} />;
  }
  return children;
}
