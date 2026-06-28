import { OpenAPI } from '@/types/generated/core/OpenAPI';
import type {
  CaseRunbookApplyResponse,
  CaseRunbookPayload,
  CaseRunbookRead,
  CaseRunbookStatus,
  PageCaseRunbookRead,
  RunbookTaskOverride,
} from '@/types/caseRunbooks';

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

function statusQuery(statuses?: CaseRunbookStatus[]): string {
  const params = new URLSearchParams();
  statuses?.forEach((status) => params.append('status', status));
  return params.toString();
}

export function listCaseRunbooks(statuses?: CaseRunbookStatus[], search?: string | null): Promise<PageCaseRunbookRead> {
  const query = new URLSearchParams(statusQuery(statuses));
  if (search) query.set('search', search);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return request<PageCaseRunbookRead>(`/api/v1/case-runbooks${suffix}`);
}

export function createCaseRunbook(payload: CaseRunbookPayload): Promise<CaseRunbookRead> {
  return request<CaseRunbookRead>('/api/v1/case-runbooks', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateCaseRunbook(id: number, payload: CaseRunbookPayload): Promise<CaseRunbookRead> {
  return request<CaseRunbookRead>(`/api/v1/case-runbooks/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function publishCaseRunbook(id: number): Promise<CaseRunbookRead> {
  return request<CaseRunbookRead>(`/api/v1/case-runbooks/${id}/publish`, { method: 'POST' });
}

export function disableCaseRunbook(id: number): Promise<CaseRunbookRead> {
  return request<CaseRunbookRead>(`/api/v1/case-runbooks/${id}/disable`, { method: 'POST' });
}

export function deleteCaseRunbook(id: number): Promise<CaseRunbookRead> {
  return request<CaseRunbookRead>(`/api/v1/case-runbooks/${id}`, { method: 'DELETE' });
}

export function applyCaseRunbook(
  caseId: number,
  runbookId: number,
  taskOverrides: RunbookTaskOverride[],
): Promise<CaseRunbookApplyResponse> {
  return request<CaseRunbookApplyResponse>(`/api/v1/case-runbooks/cases/${caseId}/apply/${runbookId}`, {
    method: 'POST',
    body: JSON.stringify({ task_overrides: taskOverrides }),
  });
}
