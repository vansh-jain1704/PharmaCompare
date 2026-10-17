import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { useAuth } from "../../context/AuthContext";

/**
 * Contextual back button. Pass `to` and `label` for the page's real parent
 * ("Back to History"); with neither it falls back to the dashboard, or to
 * the home page for visitors who are not signed in.
 *
 * It links to a fixed parent rather than calling history.back(): after a
 * redirect or a deep link, "back" can be somewhere the user never chose.
 */
export default function BackLink({ to, label }) {
  const { status } = useAuth();
  const authed = status === "authenticated";
  return (
    <Link to={to || (authed ? "/dashboard" : "/")} className="back-link">
      <ArrowLeft size={15} />
      {label || (authed ? "Back to Dashboard" : "Back to home")}
    </Link>
  );
}
