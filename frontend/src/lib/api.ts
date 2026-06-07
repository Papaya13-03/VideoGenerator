import type {
  CreateJobInput,
  Job,
  JobList,
  TokenResponse,
  User,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8080/api/v1";

const TOKEN_KEY = "vg_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  window.localStorage.removeItem(TOKEN_KEY);
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const message = body?.message || body?.detail || res.statusText;
    throw new ApiError(res.status, message);
  }
  return body as T;
}

// The backend wraps payloads as { status, message, data }. Unwrap `data` here.
function unwrap<T>(body: { data: T }): T {
  return body.data;
}

export const api = {
  register: (email: string, password: string) =>
    request<TokenResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<User>("/me"),

  createJob: (input: CreateJobInput) =>
    request<{ data: { job_id: string } }>("/jobs", {
      method: "POST",
      body: JSON.stringify(input),
    }).then((b) => unwrap(b).job_id),

  listJobs: (page = 1, pageSize = 20) =>
    request<{ data: JobList }>(`/jobs?page=${page}&page_size=${pageSize}`).then(
      (b) => unwrap(b),
    ),

  getJob: (id: string) =>
    request<{ data: Job }>(`/jobs/${id}`).then((b) => unwrap(b)),

  deleteJob: (id: string) =>
    request<{ data: unknown }>(`/jobs/${id}`, { method: "DELETE" }),
};

export { ApiError };
