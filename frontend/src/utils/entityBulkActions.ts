import { Bell, CheckSquare, Folder } from "lucide-react";
import { AlertsService } from "@/types/generated/services/AlertsService";
import { CasesService } from "@/types/generated/services/CasesService";
import { TasksService } from "@/types/generated/services/TasksService";
import type { AlertStatus } from "@/types/generated/models/AlertStatus";
import type { CaseStatus } from "@/types/generated/models/CaseStatus";
import type { TaskStatus } from "@/types/generated/models/TaskStatus";
import type { BulkUpdateResult } from "@/types/generated/models/BulkUpdateResult";
import { ALERT_STATUS_OPTIONS, CASE_STATUS_OPTIONS, TASK_STATUS_OPTIONS, type EntityType, type StatusOption } from "./statusLabels";

export type BulkUpdateFields<TStatus extends string> = {
  status?: TStatus;
  assignee?: string;
  tags?: string[];
  note?: string;
};

export type BulkEntityStatus = { alert: AlertStatus; case: CaseStatus; task: TaskStatus };

interface EntityBulkConfig<TStatus extends string> {
  statuses: readonly StatusOption<TStatus>[];
  apply: (ids: number[], fields: BulkUpdateFields<TStatus>) => Promise<BulkUpdateResult>;
}

export const entityBulkActions: { [K in EntityType]: EntityBulkConfig<BulkEntityStatus[K]> } = {
  alert: {
    statuses: ALERT_STATUS_OPTIONS.filter(({ value }) => value !== "CLOSED_DUPLICATE"),
    apply: (alert_ids, fields) => AlertsService.bulkAlertActionApiV1AlertsBulkActionsPost({
      requestBody: { action: "update", alert_ids, ...fields },
    }),
  },
  case: {
    statuses: CASE_STATUS_OPTIONS,
    apply: (entity_ids, fields) => CasesService.bulkCaseActionApiV1CasesBulkActionsPost({
      requestBody: { entity_ids, ...fields },
    }),
  },
  task: {
    statuses: TASK_STATUS_OPTIONS,
    apply: (entity_ids, fields) => TasksService.bulkTaskActionApiV1TasksBulkActionsPost({
      requestBody: { entity_ids, ...fields },
    }),
  },
};

export const bulkEntityLabels = {
  alert: { plural: "alerts", Icon: Bell },
  case: { plural: "cases", Icon: Folder },
  task: { plural: "tasks", Icon: CheckSquare },
};
