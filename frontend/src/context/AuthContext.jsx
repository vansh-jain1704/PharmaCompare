import { createContext, useContext, useEffect, useState } from "react";
import { fetchCurrentUser, loginUser, registerUser } from "../api/authApi";
import { SESSION_EXPIRED_EVENT, TOKEN_KEY } from "../api/axiosClient";

const AuthContext = createContext(null);

/**
 * Keeps the user signed in across reloads and tabs: the token lives in
 * localStorage and is re-validated against /api/auth/me on every load.
 * When the backend rejects it (tokens are short-lived) the user is returned
 * to the login page with `sessionExpired` set so it can say why.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  // "checking" avoids flashing the login page while we verify an existing token
  const [status, setStatus] = useState("checking");
  const [sessionExpired, setSessionExpired] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      setStatus("guest");
      return;
    }
    fetchCurrentUser()
      .then((res) => {
        setUser(res.data.user);
        setStatus("authenticated");
      })
      .catch((err) => {
        // A rejected token ends the session. Any other failure (e.g. the
        // server is down) just leaves the user at the login page; the saved
        // token stays so a reload can pick the session back up.
        if (err.response?.status === 401 || err.response?.status === 422) {
          localStorage.removeItem(TOKEN_KEY);
        }
        setStatus("guest");
      });
  }, []);

  useEffect(() => {
    const onExpired = () => {
      localStorage.removeItem(TOKEN_KEY);
      setUser(null);
      setSessionExpired(true);
      setStatus("guest");
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

  async function login(credentials) {
    const res = await loginUser(credentials);
    localStorage.setItem(TOKEN_KEY, res.data.access_token);
    setUser(res.data.user);
    setSessionExpired(false);
    setStatus("authenticated");
    return res.data.user;
  }

  async function register(details) {
    await registerUser(details);
    // registration does not log the user in automatically; they log in next
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    setUser(null);
    setSessionExpired(false);
    setStatus("guest");
  }

  return (
    <AuthContext.Provider value={{ user, status, sessionExpired, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside an AuthProvider");
  }
  return context;
}
