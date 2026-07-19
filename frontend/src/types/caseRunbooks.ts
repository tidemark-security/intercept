export type CaseRunbookStatus = 'DRAFT' | 'PUBLISHED' | 'DISABLED' | 'DELETED';

export type PICERLStage =
  | 'Preparation'
  | 'Identification'
  | 'Containment'
  | 'Eradication'
  | 'Recovery'
  | 'Lessons Learned';

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

export interface RunbookTaskDefinition {
  title: string;
  description?: string | null;
  picerl_stage: PICERLStage;
  relative_due_seconds?: number | null;
  priority?: 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | 'EXTREME' | null;
  tags: string[];
}

export interface CaseRunbookRead {
  id: number;
  human_id: string;
  title?: string | null;
  title_normalized?: string | null;
  description?: string | null;
  status: CaseRunbookStatus;
  case_tags: string[];
  runbook_tasks: RunbookTaskDefinition[];
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
}

export interface CaseRunbookPayload {
  title?: string | null;
  description?: string | null;
  status?: CaseRunbookStatus;
  case_tags?: string[];
  runbook_tasks?: RunbookTaskDefinition[];
}

export interface PageCaseRunbookRead {
  items: CaseRunbookRead[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export interface RunbookTaskOverride {
  index: number;
  selected?: boolean;
  assignee?: string | null;
  due_date?: string | null;
}

export interface CaseRunbookApplyResponse {
  case_id: number;
  case_human_id: string;
  runbook_id: number;
  runbook_human_id: string;
  created_task_ids: number[];
  skipped_task_titles: string[];
  duplicate_warnings: Array<{
    index: number;
    title: string;
    duplicate: boolean;
    reasons: string[];
  }>;
}
