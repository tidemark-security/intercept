export type CaseTemplateStatus = 'DRAFT' | 'PUBLISHED' | 'DISABLED' | 'DELETED';

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

export interface TemplateTaskDefinition {
  title: string;
  description?: string | null;
  picerl_stage: PICERLStage;
  relative_due_seconds?: number | null;
  priority?: 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | 'EXTREME' | null;
  tags: string[];
}

export interface CaseTemplateRead {
  id: number;
  human_id: string;
  title?: string | null;
  title_normalized?: string | null;
  description?: string | null;
  status: CaseTemplateStatus;
  case_tags: string[];
  template_tasks: TemplateTaskDefinition[];
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
}

export interface CaseTemplatePayload {
  title?: string | null;
  description?: string | null;
  status?: CaseTemplateStatus;
  case_tags?: string[];
  template_tasks?: TemplateTaskDefinition[];
}

export interface PageCaseTemplateRead {
  items: CaseTemplateRead[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export interface TemplateTaskOverride {
  index: number;
  selected?: boolean;
  assignee?: string | null;
  due_date?: string | null;
}

export interface CaseTemplateApplyResponse {
  case_id: number;
  case_human_id: string;
  template_id: number;
  template_human_id: string;
  created_task_ids: number[];
  skipped_task_titles: string[];
  duplicate_warnings: Array<{
    index: number;
    title: string;
    duplicate: boolean;
    reasons: string[];
  }>;
}
