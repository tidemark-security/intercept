import type {
  CaseRunbookApplyResponse,
  CaseRunbookPayload,
  CaseRunbookRead,
  CaseRunbookStatus,
  PageCaseRunbookRead,
  RunbookTaskOverride,
} from '@/types/caseRunbooks';
import type { CaseRunbookRead as ApiCaseRunbookRead } from '@/types/generated/models/CaseRunbookRead';
import { CaseRunbooksService } from '@/types/generated/services/CaseRunbooksService';
import { rethrowApiRequestError } from './apiRequestError';

function normalizeCaseRunbook(runbook: ApiCaseRunbookRead): CaseRunbookRead {
  return {
    ...runbook,
    status: runbook.status ?? 'DRAFT',
    case_tags: runbook.case_tags ?? [],
    runbook_tasks: (runbook.runbook_tasks ?? []).map((task) => ({
      ...task,
      tags: task.tags ?? [],
    })),
  };
}

export async function listCaseRunbooks(statuses?: CaseRunbookStatus[], search?: string | null): Promise<PageCaseRunbookRead> {
  const page = await CaseRunbooksService.listCaseRunbooksApiV1CaseRunbooksGet({
    status: statuses,
    search: search || undefined,
  }).catch(rethrowApiRequestError);
  return { ...page, items: page.items.map(normalizeCaseRunbook) };
}

export async function createCaseRunbook(payload: CaseRunbookPayload): Promise<CaseRunbookRead> {
  const runbook = await CaseRunbooksService.createCaseRunbookApiV1CaseRunbooksPost({ requestBody: payload })
    .catch(rethrowApiRequestError);
  return normalizeCaseRunbook(runbook);
}

export async function updateCaseRunbook(id: number, payload: CaseRunbookPayload): Promise<CaseRunbookRead> {
  const runbook = await CaseRunbooksService.updateCaseRunbookApiV1CaseRunbooksRunbookIdPut({
    runbookId: id,
    requestBody: payload,
  }).catch(rethrowApiRequestError);
  return normalizeCaseRunbook(runbook);
}

export async function publishCaseRunbook(id: number): Promise<CaseRunbookRead> {
  const runbook = await CaseRunbooksService.publishCaseRunbookApiV1CaseRunbooksRunbookIdPublishPost({ runbookId: id })
    .catch(rethrowApiRequestError);
  return normalizeCaseRunbook(runbook);
}

export async function disableCaseRunbook(id: number): Promise<CaseRunbookRead> {
  const runbook = await CaseRunbooksService.disableCaseRunbookApiV1CaseRunbooksRunbookIdDisablePost({ runbookId: id })
    .catch(rethrowApiRequestError);
  return normalizeCaseRunbook(runbook);
}

export async function deleteCaseRunbook(id: number): Promise<CaseRunbookRead> {
  const runbook = await CaseRunbooksService.deleteCaseRunbookApiV1CaseRunbooksRunbookIdDelete({ runbookId: id })
    .catch(rethrowApiRequestError);
  return normalizeCaseRunbook(runbook);
}

export async function applyCaseRunbook(
  caseId: number,
  runbookId: number,
  taskOverrides: RunbookTaskOverride[],
): Promise<CaseRunbookApplyResponse> {
  const response = await CaseRunbooksService.applyCaseRunbookApiV1CaseRunbooksCasesCaseIdApplyRunbookIdPost({
    caseId,
    runbookId,
    requestBody: { task_overrides: taskOverrides },
  }).catch(rethrowApiRequestError);

  return {
    ...response,
    duplicate_warnings: (response.duplicate_warnings ?? []).map((warning) => ({
      ...warning,
      duplicate: warning.duplicate ?? false,
      reasons: warning.reasons ?? [],
    })),
  };
}
