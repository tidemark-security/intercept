import { OpenAPI } from '@/types/generated/core/OpenAPI';

export type ContextCriterionType =
  | 'ALERT_SOURCE'
  | 'ACTOR'
  | 'SYSTEM'
  | 'OBSERVABLE'
  | 'TAG';

export interface ContextCriterion {
  type: ContextCriterionType;
  value: string;
}

export interface ContextEntry {
  id: number;
  criteria: ContextCriterion[];
  body: string;
  author: string;
  created_at: string;
  updated_at: string;
  expires_at: string;
  expired_at?: string | null;
}

export interface ContextEntryPayload {
  criteria?: ContextCriterion[];
  body: string;
  expires_at: string;
}

function getCookieValue(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const cookie = document.cookie.split('; ').find((entry) => entry.startsWith(`${name}=`));
  return cookie ? decodeURIComponent(cookie.slice(name.length + 1)) : null;
}

async function getErrorMessage(response: Response): Promise<string> {
  const payload = await response.json().catch(() => null);
  const detail = payload && typeof payload === 'object' && 'detail' in payload ? payload.detail : null;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') {
    return detail.message;
  }
  return `Request failed with status ${response.status}`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  if (init.body) {
    headers.set('Content-Type', 'application/json');
  }
  const csrfToken = getCookieValue('XSRF-TOKEN');
  if (csrfToken) {
    headers.set('X-XSRF-TOKEN', csrfToken);
  }

  const response = await fetch(`${OpenAPI.BASE}${path}`, {
    ...init,
    headers,
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }
  return response.json() as Promise<T>;
}

export function listContextEntries(includeExpired = false): Promise<ContextEntry[]> {
  const query = includeExpired ? '?include_expired=true' : '';
  return request<ContextEntry[]>(`/api/v1/context-entries${query}`);
}

export function createContextEntry(payload: ContextEntryPayload): Promise<ContextEntry> {
  return request<ContextEntry>('/api/v1/context-entries', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateContextEntry(id: number, payload: Partial<ContextEntryPayload>): Promise<ContextEntry> {
  return request<ContextEntry>(`/api/v1/context-entries/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function expireContextEntry(id: number): Promise<ContextEntry> {
  return request<ContextEntry>(`/api/v1/context-entries/${id}/expire`, {
    method: 'POST',
  });
}
