export type TaskDueStatus = 'overdue' | 'due_soon' | null;

export function getTaskDueStatus(
  dueDateValue: string | null | undefined,
  status: string | null | undefined,
): TaskDueStatus {
  if (!dueDateValue || status === 'DONE') {
    return null;
  }

  const dueDate = new Date(dueDateValue);
  const dueTime = dueDate.getTime();

  if (Number.isNaN(dueTime)) {
    return null;
  }

  const now = new Date();
  const oneDayFromNow = new Date(now.getTime() + 24 * 60 * 60 * 1000);

  if (dueDate < now) {
    return 'overdue';
  }

  if (dueDate <= oneDayFromNow) {
    return 'due_soon';
  }

  return null;
}