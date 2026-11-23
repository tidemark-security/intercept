import { ApiError } from '@/types/generated/core/ApiError';

export function rethrowApiRequestError(error: unknown): never {
  if (!(error instanceof ApiError)) throw error;

  const body: unknown = error.body;
  const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : null;
  if (typeof detail === 'string') throw new Error(detail);
  if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') {
    throw new Error(detail.message);
  }
  throw new Error(`Request failed with status ${error.status}`);
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.body && typeof error.body === "object") {
    const { detail, message } = error.body;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail.message === "string") return detail.message;
    if (typeof message === "string") return message;
  }
  return error instanceof Error && error.message ? error.message : fallback;
}
