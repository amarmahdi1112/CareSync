import { config } from '../config';

export class ApiError extends Error {
  readonly status: number;
  readonly details: unknown;

  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
  }
}

type QueryValue = string | number | boolean | null | undefined;

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const base = config.apiUrl.replace(/\/$/, '');
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const url = new URL(`${base}${normalizedPath}`);
  Object.entries(query || {}).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== '') {
      url.searchParams.set(key, String(value));
    }
  });
  return url.toString();
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  query?: Record<string, QueryValue>,
): Promise<T> {
  const token = localStorage.getItem('token');
  const headers = new Headers(options.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await fetch(buildUrl(path, query), { ...options, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const message = payload?.detail || payload?.message || `Request failed (${response.status})`;
    if (response.status === 401) window.dispatchEvent(new Event('caresync:unauthorized'));
    throw new ApiError(response.status, message, payload);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function upload<T>(path: string, file: File): Promise<T> {
  const token = localStorage.getItem('token');
  const headers = new Headers({ 'Content-Type': file.type });
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(buildUrl(path), { method: 'PUT', headers, body: file });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiError(response.status, payload?.detail || `Upload failed (${response.status})`, payload);
  }
  return response.json() as Promise<T>;
}

export interface ApiRole {
  id: number;
  name: string;
  description: string | null;
  permissions: Array<{ id: number; name: string; description: string | null }>;
}

export interface ApiUser {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: ApiRole;
  organization_id: string | null;
  is_active: boolean;
}

export const api = {
  get: <T>(path: string, query?: Record<string, QueryValue>) => request<T>(path, {}, query),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  upload,
  delete: (path: string, query?: Record<string, QueryValue>) =>
    request<void>(path, { method: 'DELETE' }, query),
  auth: {
    login: (email: string, password: string) =>
      request<{ access_token: string; token_type: string; user: ApiUser }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      }),
    me: () => request<ApiUser>('/auth/me'),
  },
  resources: {
    list: <T>(resource: string, query?: Record<string, QueryValue>) =>
      request<T[]>(`/resources/${resource}`, {}, query),
    get: <T>(resource: string, id: string) => request<T>(`/resources/${resource}/${id}`),
    create: <T>(resource: string, body: unknown) =>
      request<T>(`/resources/${resource}`, { method: 'POST', body: JSON.stringify(body) }),
    update: <T>(resource: string, id: string, body: unknown) =>
      request<T>(`/resources/${resource}/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      }),
    remove: (resource: string, id: string) =>
      request<void>(`/resources/${resource}/${id}`, { method: 'DELETE' }, { confirm: true }),
  },
};
