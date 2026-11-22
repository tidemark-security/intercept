import type { ContextCriterion } from '@/types/generated/models/ContextCriterion';
import type { ContextEntryCreate } from '@/types/generated/models/ContextEntryCreate';
import type { ContextEntryRead } from '@/types/generated/models/ContextEntryRead';
import { ContextEntriesService } from '@/types/generated/services/ContextEntriesService';
import { rethrowApiRequestError } from './apiRequestError';

export type { ContextCriterion } from '@/types/generated/models/ContextCriterion';
export type { ContextCriterionType } from '@/types/generated/models/ContextCriterionType';

export type ContextEntry = Omit<ContextEntryRead, 'criteria'> & { criteria: ContextCriterion[] };
export type ContextEntryPayload = ContextEntryCreate;

function normalizeContextEntry(entry: ContextEntryRead): ContextEntry {
  return { ...entry, criteria: entry.criteria ?? [] };
}

export async function listContextEntries(includeExpired = false): Promise<ContextEntry[]> {
  const entries = await ContextEntriesService.listContextEntriesApiV1ContextEntriesGet({ includeExpired })
    .catch(rethrowApiRequestError);
  return entries.map(normalizeContextEntry);
}

export async function createContextEntry(payload: ContextEntryPayload): Promise<ContextEntry> {
  const entry = await ContextEntriesService.createContextEntryApiV1ContextEntriesPost({ requestBody: payload })
    .catch(rethrowApiRequestError);
  return normalizeContextEntry(entry);
}

export async function updateContextEntry(id: number, payload: Partial<ContextEntryPayload>): Promise<ContextEntry> {
  const entry = await ContextEntriesService.updateContextEntryApiV1ContextEntriesEntryIdPut({
    entryId: id,
    requestBody: payload,
  }).catch(rethrowApiRequestError);
  return normalizeContextEntry(entry);
}

export async function expireContextEntry(id: number): Promise<ContextEntry> {
  const entry = await ContextEntriesService.expireContextEntryApiV1ContextEntriesEntryIdExpirePost({ entryId: id })
    .catch(rethrowApiRequestError);
  return normalizeContextEntry(entry);
}
