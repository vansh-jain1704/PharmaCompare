import axiosClient from "./axiosClient";

export function registerUser({ name, email, phone, password }) {
  return axiosClient.post("/api/auth/register", { name, email, phone, password });
}

export function loginUser({ email, password }) {
  return axiosClient.post("/api/auth/login", { email, password });
}

export function fetchCurrentUser() {
  return axiosClient.get("/api/auth/me");
}

export function updateAllergies(allergies) {
  return axiosClient.put("/api/auth/me/allergies", { allergies });
}
