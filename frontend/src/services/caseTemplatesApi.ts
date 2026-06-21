import { OpenAPI } from '@/types/generated/core/OpenAPI';
import type {
  CaseTemplateApplyResponse,
  CaseTemplatePayload,
  CaseTemplateRead,
  CaseTemplateStatus,
  PageCaseTemplateRead,
  TemplateTaskOverride,
} from '@/types/caseTemplates';

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

function statusQuery(statuses?: CaseTemplateStatus[]): string {
  const params = new URLSearchParams();
  statuses?.forEach((status) => params.append('status', status));
  return params.toString();
}

export function listCaseTemplates(statuses?: CaseTemplateStatus[], search?: string | null): Promise<PageCaseTemplateRead> {
  const query = new URLSearchParams(statusQuery(statuses));
  if (search) query.set('search', search);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return request<PageCaseTemplateRead>(`/api/v1/case-templates${suffix}`);
}

export function createCaseTemplate(payload: CaseTemplatePayload): Promise<CaseTemplateRead> {
  return request<CaseTemplateRead>('/api/v1/case-templates', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateCaseTemplate(id: number, payload: CaseTemplatePayload): Promise<CaseTemplateRead> {
  return request<CaseTemplateRead>(`/api/v1/case-templates/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function publishCaseTemplate(id: number): Promise<CaseTemplateRead> {
  return request<CaseTemplateRead>(`/api/v1/case-templates/${id}/publish`, { method: 'POST' });
}

export function disableCaseTemplate(id: number): Promise<CaseTemplateRead> {
  return request<CaseTemplateRead>(`/api/v1/case-templates/${id}/disable`, { method: 'POST' });
}

export function deleteCaseTemplate(id: number): Promise<CaseTemplateRead> {
  return request<CaseTemplateRead>(`/api/v1/case-templates/${id}`, { method: 'DELETE' });
}

export function applyCaseTemplate(
  caseId: number,
  templateId: number,
  taskOverrides: TemplateTaskOverride[],
): Promise<CaseTemplateApplyResponse> {
  return request<CaseTemplateApplyResponse>(`/api/v1/case-templates/cases/${caseId}/apply/${templateId}`, {
    method: 'POST',
    body: JSON.stringify({ task_overrides: taskOverrides }),
  });
}
