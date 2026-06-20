import type { AlertStatus } from "@/types/generated/models/AlertStatus";
import type { CaseStatus } from "@/types/generated/models/CaseStatus";
import type { TaskStatus } from "@/types/generated/models/TaskStatus";

export type EntityType = "alert" | "case" | "task";

export interface StatusOption<TStatus extends string = string> {
  value: TStatus;
  label: string;
}

export type ClosedAlertStatus = Extract<
  AlertStatus,
  | "CLOSED_TP"
  | "CLOSED_BP"
  | "CLOSED_FP"
  | "CLOSED_UNRESOLVED"
  | "CLOSED_DUPLICATE"
>;

export const ALERT_STATUS_LABELS: Record<AlertStatus, string> = {
  NEW: "New",
  IN_PROGRESS: "In Progress",
  ESCALATED: "Escalated",
  CLOSED_TP: "Closed (True Positive)",
  CLOSED_BP: "Closed (Benign Positive)",
  CLOSED_FP: "Closed (False Positive)",
  CLOSED_UNRESOLVED: "Closed (Unresolved)",
  CLOSED_DUPLICATE: "Closed (Duplicate)",
};

export const CASE_STATUS_LABELS: Record<CaseStatus, string> = {
  NEW: "New",
  IN_PROGRESS: "In Progress",
  CLOSED: "Closed",
};

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  TODO: "To Do",
  IN_PROGRESS: "In Progress",
  DONE: "Done",
};

export const ALERT_STATUS_OPTIONS: StatusOption<AlertStatus>[] = [
  { value: "NEW", label: ALERT_STATUS_LABELS.NEW },
  { value: "IN_PROGRESS", label: ALERT_STATUS_LABELS.IN_PROGRESS },
  { value: "ESCALATED", label: ALERT_STATUS_LABELS.ESCALATED },
  { value: "CLOSED_TP", label: ALERT_STATUS_LABELS.CLOSED_TP },
  { value: "CLOSED_BP", label: ALERT_STATUS_LABELS.CLOSED_BP },
  { value: "CLOSED_FP", label: ALERT_STATUS_LABELS.CLOSED_FP },
  { value: "CLOSED_UNRESOLVED", label: ALERT_STATUS_LABELS.CLOSED_UNRESOLVED },
  { value: "CLOSED_DUPLICATE", label: ALERT_STATUS_LABELS.CLOSED_DUPLICATE },
];

export const CLOSED_ALERT_STATUS_OPTIONS: StatusOption<ClosedAlertStatus>[] =
  ALERT_STATUS_OPTIONS.filter((option): option is StatusOption<ClosedAlertStatus> =>
    option.value.startsWith("CLOSED_"),
  );

export const CASE_STATUS_OPTIONS: StatusOption<CaseStatus>[] = [
  { value: "NEW", label: CASE_STATUS_LABELS.NEW },
  { value: "IN_PROGRESS", label: CASE_STATUS_LABELS.IN_PROGRESS },
  { value: "CLOSED", label: CASE_STATUS_LABELS.CLOSED },
];

export const TASK_STATUS_OPTIONS: StatusOption<TaskStatus>[] = [
  { value: "TODO", label: TASK_STATUS_LABELS.TODO },
  { value: "IN_PROGRESS", label: TASK_STATUS_LABELS.IN_PROGRESS },
  { value: "DONE", label: TASK_STATUS_LABELS.DONE },
];

export function formatAlertStatusLabel(status: AlertStatus): string {
  return ALERT_STATUS_LABELS[status];
}

export function formatCaseStatusLabel(status: CaseStatus): string {
  return CASE_STATUS_LABELS[status];
}

export function formatTaskStatusLabel(status: TaskStatus): string {
  return TASK_STATUS_LABELS[status];
}

export function formatEntityStatusLabel(
  entityType: EntityType,
  status: AlertStatus | CaseStatus | TaskStatus,
): string {
  if (entityType === "alert") {
    return ALERT_STATUS_LABELS[status as AlertStatus] ?? status;
  }
  if (entityType === "case") {
    return CASE_STATUS_LABELS[status as CaseStatus] ?? status;
  }
  return TASK_STATUS_LABELS[status as TaskStatus] ?? status;
}
