import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

/** Password field with a show/hide toggle (replaces the confirm-password box). */
export default function PasswordInput(props) {
  const [shown, setShown] = useState(false);
  return (
    <div className="password-input">
      <input {...props} type={shown ? "text" : "password"} />
      <button
        type="button" className="password-toggle" onClick={() => setShown((s) => !s)}
        aria-label={shown ? "Hide password" : "Show password"} aria-pressed={shown}
      >
        {shown ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </div>
  );
}
