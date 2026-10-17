import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { onboardingKey } from "../utils/onboarding";

/**
 * Login and Register make no sense for someone already signed in. A user who
 * just logged in goes back to the page they were headed for (if a protected
 * route sent them here), otherwise to the one-time allergy question the first
 * time, otherwise to the dashboard.
 */
export default function GuestOnly({ children }) {
  const { status, user } = useAuth();
  const location = useLocation();
  if (status !== "authenticated") return children;

  const from = typeof location.state?.from === "string" ? location.state.from : null;
  const onboarded = user?.user_id != null && localStorage.getItem(onboardingKey(user.user_id));
  return <Navigate to={onboarded ? (from || "/dashboard") : "/onboarding"} replace />;
}
