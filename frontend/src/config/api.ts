import axios from 'axios';
import type { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios';

// ─── Base URL ────────────────────────────────────────────────────────────────
// Vite uses import.meta.env for env vars (prefixed with VITE_)
const BASE_URL = import.meta.env.VITE_API_URL ?? import.meta.env.REACT_APP_API_URL;
if (!BASE_URL) {
  console.warn("API URL is not defined in environment variables. Falling back to relative path.");
}

// ─── Axios instance ──────────────────────────────────────────────────────────
const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 10_000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ─── Request interceptor: log outgoing requests ──────────────────────────────
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    if (import.meta.env.DEV) {
      console.log(`[API] ${config.method?.toUpperCase()} ${config.url}`);
    }
    return config;
  },
  (error: AxiosError) => {
    console.error('[API] Request error:', error.message);
    return Promise.reject(error);
  },
);

// ─── Response interceptor: log errors ────────────────────────────────────────
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const status = error.response?.status;
    const url = error.config?.url;
    const detail = (error.response?.data as Record<string, unknown>)?.detail;

    console.error(`[API] Error ${status} on ${url}:`, detail ?? error.message);

    // Xử lý chung các mã lỗi hệ thống
    if (status === 401 || status === 403 || status === 500) {
      window.dispatchEvent(new CustomEvent('app-toast', { 
        detail: { type: 'error', message: `Lỗi hệ thống (${status}): ${detail ?? error.message}` } 
      }));
    }

    return Promise.reject(error);
  },
);

export { api, BASE_URL };
export default api;
