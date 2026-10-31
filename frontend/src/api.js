/**
 * Thin API client for the Brightloop FastAPI backend.
 *
 * Local dev goes through the Vite proxy (`/api` -> 127.0.0.1:8000), so the
 * default base is relative. For a deployed frontend set VITE_API_BASE to the
 * full API root, e.g. https://api.example.com/api/v1.
 */
export const API_BASE = import.meta.env.VITE_API_BASE || "/api/v1";

const TOKEN_KEY = "brightloop_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function request(path, { method = "GET", body, auth = true } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (auth && token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    const error = new Error(
      "Cannot reach the API. Start the backend on port 8000 and try again.",
    );
    error.status = 0;
    throw error;
  }

  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!response.ok) {
    const detail = data && typeof data === "object" ? data.detail : data;
    let message = `Request failed (${response.status})`;
    if (typeof detail === "string") {
      message = detail;
    } else if (Array.isArray(detail)) {
      message = detail
        .map((item) => item?.msg || item?.message || JSON.stringify(item))
        .join(", ");
    } else if (detail && typeof detail === "object") {
      message = JSON.stringify(detail);
    }
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }

  return data;
}

const listQuery = (pageSize = 100) => `?page=1&page_size=${pageSize}`;

export const api = {
  login: (email, password) =>
    request("/auth/login", { method: "POST", body: { email, password }, auth: false }),
  register: (payload) =>
    request("/auth/register", { method: "POST", body: payload, auth: false }),
  me: () => request("/auth/me"),
  subscriptions: (pageSize = 100) => request(`/subscriptions${listQuery(pageSize)}`),
  createSubscription: (payload) =>
    request("/subscriptions", { method: "POST", body: payload }),
  plans: (pageSize = 100) => request(`/plans${listQuery(pageSize)}`),
  customers: (pageSize = 100) => request(`/customers${listQuery(pageSize)}`),
  products: (pageSize = 100) => request(`/products${listQuery(pageSize)}`),
};
