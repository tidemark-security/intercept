/**
 * Type definitions for alert and case filtering
 */

import type { AlertStatus } from './generated/models/AlertStatus';
import type { CaseStatus } from './generated/models/CaseStatus';
import type { TaskStatus } from './generated/models/TaskStatus';

/**
 * Date range filter value
 * All dates are stored as UTC ISO8601 strings with 'Z' suffix
 * Format: "YYYY-MM-DDTHH:mm:ssZ" (e.g., "2025-10-20T14:30:00Z")
 * 
 * Supported formats for input:
 * - Relative expressions: "-15m", "-1h", "-24h", "-7d", "-30d", "now"
 * - ISO8601: "YYYY-MM-DDTHH:mm:ss" (with or without 'T', with or without 'Z')
 * - Native datetime-local picker values
 * 
 * All dates are converted to UTC before storage and API transmission.
 */
export interface DateRange {
  /** Start date in UTC ISO8601 format with 'Z' suffix (e.g., "2025-10-20T14:30:00Z") */
  start: string;
  /** End date in UTC ISO8601 format with 'Z' suffix (e.g., "2025-10-20T18:30:00Z") */
  end: string;
  /** Optional relative expression for display purposes (e.g., "-7d" for "Last 7 days", "custom" for custom ranges) */
  preset?: string;
}

/**
 * Alert list filter state
 * Used to control CaseAlertFilterCompact and filter alerts API requests
 */
export interface FilterState {
  /** Search query for alert description/source */
  search: string;
  /**
   * Array of selected assignee usernames for multi-select filtering, or null for no filter
   * Supports selecting multiple assignees simultaneously (e.g., ['admin', 'analyst'])
   * Empty array is treated as null (no filter applied)
   */
  assignee: string[] | null;
  /**
   * Array of selected alert statuses for multi-select filtering, or null for no filter
   * Supports selecting multiple statuses simultaneously (e.g., ['new', 'in_progress'])
   * Empty array is treated as null (no filter applied)
   */
  status: AlertStatus[] | null;
  /** 
   * Selected date range, or null for "All time" (no date filtering)
   * When null, the backend will return all alerts regardless of date
   */
  dateRange: DateRange | null;
}

/**
 * Case list filter state
 * Used to control filter components and filter cases API requests
 */
export interface CaseFilterState {
  /** Search query for case title/description */
  search: string;
  /**
   * Array of selected assignee usernames for multi-select filtering, or null for no filter
   * Supports selecting multiple assignees simultaneously (e.g., ['admin', 'analyst'])
   * Empty array is treated as null (no filter applied)
   */
  assignee: string[] | null;
  /**
   * Array of selected case statuses for multi-select filtering, or null for no filter
   * Supports selecting multiple statuses simultaneously (e.g., ['new', 'in_progress'])
   * Empty array is treated as null (no filter applied)
   */
  status: CaseStatus[] | null;
  /** 
   * Selected date range, or null for "All time" (no date filtering)
   * When null, the backend will return all cases regardless of date
   */
  dateRange: DateRange | null;
}

/**
 * Task list filter state
 * Used to control filter components and filter tasks API requests
 */
export interface TaskFilterState {
  /** Search query for task title/description */
  search: string;
  /**
   * Array of selected assignee usernames for multi-select filtering, or null for no filter
   * Supports selecting multiple assignees simultaneously (e.g., ['admin', 'analyst'])
   * Empty array is treated as null (no filter applied)
   */
  assignee: string[] | null;
  /**
   * Array of selected task statuses for multi-select filtering, or null for no filter
   * Supports selecting multiple statuses simultaneously (e.g., ['TODO', 'IN_PROGRESS'])
   * Empty array is treated as null (no filter applied)
   */
  status: TaskStatus[] | null;
  /** 
   * Selected date range, or null for "All time" (no date filtering)
   * When null, the backend will return all tasks regardless of date
   */
  dateRange: DateRange | null;
}
