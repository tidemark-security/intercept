import type { CaseRunbookApplyResponse as ApiCaseRunbookApplyResponse } from '@/types/generated/models/CaseRunbookApplyResponse';
import type { CaseRunbookApplyTaskWarning } from '@/types/generated/models/CaseRunbookApplyTaskWarning';
import type { CaseRunbookCreate } from '@/types/generated/models/CaseRunbookCreate';
import type { CaseRunbookRead as ApiCaseRunbookRead } from '@/types/generated/models/CaseRunbookRead';
import type { CaseRunbookStatus } from '@/types/generated/models/CaseRunbookStatus';
import type { Page_CaseRunbookRead_ } from '@/types/generated/models/Page_CaseRunbookRead_';
import type { PICERLStage } from '@/types/generated/models/PICERLStage';
import type { RunbookTaskDefinition as ApiRunbookTaskDefinition } from '@/types/generated/models/RunbookTaskDefinition';

export type { CaseRunbookStatus, PICERLStage };
export type { RunbookTaskOverride } from '@/types/generated/models/RunbookTaskOverride';

export const PICERL_STAGES: PICERLStage[] = [
  'Preparation',
  'Identification',
  'Containment',
  'Eradication',
  'Recovery',
  'Lessons Learned',
];

export const PICERL_STAGE_LABELS: Record<PICERLStage, string> = {
  Preparation: 'Preparation',
  Identification: 'Identification',
  Containment: 'Containment',
  Eradication: 'Eradication',
  Recovery: 'Recovery',
  'Lessons Learned': 'Lessons Learned',
};

export type RunbookTaskDefinition = Required<Pick<ApiRunbookTaskDefinition, 'tags'>> & ApiRunbookTaskDefinition;

export type CaseRunbookRead = Omit<ApiCaseRunbookRead, 'human_id' | 'status' | 'case_tags' | 'runbook_tasks'> & {
  human_id: ApiCaseRunbookRead['human_id'];
  status: CaseRunbookStatus;
  case_tags: string[];
  runbook_tasks: RunbookTaskDefinition[];
};

export type CaseRunbookPayload = Omit<CaseRunbookCreate, 'status' | 'runbook_tasks'> & {
  status?: CaseRunbookStatus;
  runbook_tasks?: RunbookTaskDefinition[];
};

export type PageCaseRunbookRead = Omit<Page_CaseRunbookRead_, 'items'> & {
  items: CaseRunbookRead[];
};

export type CaseRunbookApplyResponse = Omit<ApiCaseRunbookApplyResponse, 'duplicate_warnings'> & {
  duplicate_warnings: Required<CaseRunbookApplyTaskWarning>[];
};
