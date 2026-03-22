/**
 * Status Helper Utilities
 * 
 * Maps between API enum values (UPPERCASE) and UI display values (lowercase).
 * The backend uses UPPERCASE enum values, while the UI components use lowercase
 * for their internal styling logic.
 */

import type { CaseStatus } from '@/types/generated/models/CaseStatus';
import type { AlertStatus } from '@/types/generated/models/AlertStatus';
import type { TaskStatus } from '@/types/generated/models/TaskStatus';
import type { Priority } from '@/types/generated/models/Priority';

// UI state type used by UI components (MenuCard, State, etc.)
export type UIState = 
  | 'new' 
  | 'in_progress' 
  | 'escalated' 
  | 'closed' 
  | 'closed_true_positive' 
  | 'closed_benign_positive' 
  | 'closed_false_positive' 
  | 'closed_unresolved' 
  | 'closed_duplicate'
  | 'tsk_todo'
  | 'tsk_in_progress'
  | 'tsk_done';

// UI priority type used by UI components (matches Priority component props)
export type UIPriority = 'info' | 'low' | 'medium' | 'high' | 'critical' | 'extreme';

/**
 * Convert API CaseStatus (UPPERCASE) to UI state (lowercase)
 * Returns MenuCardState which is compatible with MenuCard component
 */
export function caseStatusToUIState(status: CaseStatus): MenuCardState {
  const map: Record<CaseStatus, MenuCardState> = {
    'NEW': 'new',
    'IN_PROGRESS': 'in_progress',
    'CLOSED': 'closed',
  };
  return map[status] || 'new';
}

/**
 * Convert API AlertStatus (UPPERCASE) to UI state (lowercase)
 * Returns MenuCardState which is compatible with MenuCard component
 */
export function alertStatusToUIState(status: AlertStatus): MenuCardState {
  const map: Record<AlertStatus, MenuCardState> = {
    'NEW': 'new',
    'IN_PROGRESS': 'in_progress',
    'ESCALATED': 'escalated',
    'CLOSED_TP': 'closed_true_positive',
    'CLOSED_BP': 'closed_benign_positive',
    'CLOSED_FP': 'closed_false_positive',
    'CLOSED_UNRESOLVED': 'closed_unresolved',
    'CLOSED_DUPLICATE': 'closed_duplicate',
  };
  return map[status] || 'new';
}

/**
 * Convert API TaskStatus (UPPERCASE) to UI state (lowercase)
 */
export function taskStatusToUIState(status: TaskStatus): UIState {
  const map: Record<TaskStatus, UIState> = {
    'TODO': 'tsk_todo',
    'IN_PROGRESS': 'tsk_in_progress',
    'DONE': 'tsk_done',
  };
  return map[status] || 'tsk_todo';
}

/**
 * Convert API Priority (UPPERCASE) to UI priority (lowercase)
 */
export function priorityToUIPriority(priority: Priority | null | undefined): UIPriority {
  if (!priority) return 'medium';
  const map: Record<Priority, UIPriority> = {
    'INFO': 'info',
    'LOW': 'low',
    'MEDIUM': 'medium',
    'HIGH': 'high',
    'CRITICAL': 'critical',
    'EXTREME': 'extreme',
  };
  return map[priority] || 'medium';
}

// MenuCard-compatible state type (subset of UIState that MenuCard component accepts)
export type MenuCardState = 
  | 'new' 
  | 'in_progress' 
  | 'escalated' 
  | 'closed' 
  | 'closed_true_positive' 
  | 'closed_benign_positive' 
  | 'closed_false_positive' 
  | 'closed_unresolved' 
  | 'closed_duplicate'
  | 'tsk_todo'
  | 'tsk_in_progress'
  | 'tsk_done';

/**
 * Convert task UIState to MenuCard-compatible state
 * Task states are now directly supported by MenuCard
 */
export function taskStateToMenuCardState(state: UIState): MenuCardState {
  const map: Record<string, MenuCardState> = {
    'tsk_todo': 'tsk_todo',
    'tsk_in_progress': 'tsk_in_progress',
    'tsk_done': 'tsk_done',
  };
  return map[state] || 'tsk_todo';
}

/**
 * Convert UI state (lowercase) to API CaseStatus (UPPERCASE)
 */
export function uiStateToCaseStatus(state: UIState): CaseStatus {
  const map: Partial<Record<UIState, CaseStatus>> = {
    'new': 'NEW',
    'in_progress': 'IN_PROGRESS',
    'closed': 'CLOSED',
  };
  return map[state] || 'NEW';
}

/**
 * Convert UI state (lowercase) to API AlertStatus (UPPERCASE)
 */
export function uiStateToAlertStatus(state: UIState): AlertStatus {
  const map: Partial<Record<UIState, AlertStatus>> = {
    'new': 'NEW',
    'in_progress': 'IN_PROGRESS',
    'escalated': 'ESCALATED',
    'closed_true_positive': 'CLOSED_TP',
    'closed_benign_positive': 'CLOSED_BP',
    'closed_false_positive': 'CLOSED_FP',
    'closed_unresolved': 'CLOSED_UNRESOLVED',
    'closed_duplicate': 'CLOSED_DUPLICATE',
  };
  return map[state] || 'NEW';
}

/**
 * Convert UI state (lowercase) to API TaskStatus (UPPERCASE)
 */
export function uiStateToTaskStatus(state: UIState): TaskStatus {
  const map: Partial<Record<UIState, TaskStatus>> = {
    'tsk_todo': 'TODO',
    'tsk_in_progress': 'IN_PROGRESS',
    'tsk_done': 'DONE',
  };
  return map[state] || 'TODO';
}
