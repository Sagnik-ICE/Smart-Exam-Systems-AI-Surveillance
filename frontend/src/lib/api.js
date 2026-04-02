import axios from "axios";

const browserHost = typeof window !== "undefined" ? window.location.hostname : "127.0.0.1";
const defaultApiBaseUrl = `http://${browserHost || "127.0.0.1"}:8000`;

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || defaultApiBaseUrl
});

const TOKEN_KEY = "exam_auth_token";

function getStorage() {
  if (typeof window !== "undefined" && window.sessionStorage) {
    return window.sessionStorage;
  }
  return localStorage;
}

export function setAuthToken(token) {
  const storage = getStorage();
  if (!token) {
    storage.removeItem(TOKEN_KEY);
    return;
  }
  storage.setItem(TOKEN_KEY, token);
}

export function getAuthToken() {
  return getStorage().getItem(TOKEN_KEY);
}

api.interceptors.request.use((config) => {
  const token = getAuthToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;

