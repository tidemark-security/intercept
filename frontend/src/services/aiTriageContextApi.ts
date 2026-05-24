import { OpenAPI } from '@/types/generated/core/OpenAPI';

export type AITriageContextScopeType =
  | 'GLOBAL'
  | 'ALERT_SOURCE'
  | 'CASE'
  | 'USER_ACCOUNT'
  | 'HOST_SYSTEM'
  | 'OBSERVABLE'
  | 'TAG';

export interface AITriageContextScope {
  type: AITriageContextScopeType;
  value?: string | null;
}

export interface AITriageContextEntry {
  id: number;
  scope: AITriageContextScope;
  body: string;
  author: string;
  created_at: string;
  updated_at: string;
  expires_at: string;
  expired_at?: string | null;
}

export interface AITriageContextPayload {
  scope: AITriageContextScope;
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

export function listAITriageContext(includeExpired = false): Promise<AITriageContextEntry[]> {
  const query = includeExpired ? '?include_expired=true' : '';
  return request<AITriageContextEntry[]>(`/api/v1/ai-triage-context${query}`);
}

export function createAITriageContext(payload: AITriageContextPayload): Promise<AITriageContextEntry> {
  return request<AITriageContextEntry>('/api/v1/ai-triage-context', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateAITriageContext(id: number, payload: Partial<AITriageContextPayload>): Promise<AITriageContextEntry> {
  return request<AITriageContextEntry>(`/api/v1/ai-triage-context/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function expireAITriageContext(id: number): Promise<AITriageContextEntry> {
  return request<AITriageContextEntry>(`/api/v1/ai-triage-context/${id}/expire`, {
    method: 'POST',
  });
}
