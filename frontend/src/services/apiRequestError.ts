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
