import axios from "axios";

export const TOKEN_KEY = "pharmacompare_token";
export const SESSION_EXPIRED_EVENT = "pharmacompare:session-expired";

const axiosClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Attach the saved JWT (if any) to every outgoing request automatically,
// so individual pages never have to remember to do this themselves.
axiosClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// A 401 on anything except the login call itself means the saved token is no
// longer valid (the backend issues short-lived tokens). Tell the app once so
// it can send the user to the login page - and bring them back afterwards -
// instead of leaving every page showing a vague error.
axiosClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const url = error.config?.url || "";
    const hadToken = !!localStorage.getItem(TOKEN_KEY);
    if (error.response?.status === 401 && hadToken && !url.includes("/api/auth/login")) {
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
    return Promise.reject(error);
  },
);

export default axiosClient;
