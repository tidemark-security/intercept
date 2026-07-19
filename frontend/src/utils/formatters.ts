/**
 * Utility functions for formatting data values
 */

import type { AlertStatus } from '../types/generated/models/AlertStatus';
import { formatAlertStatusLabel } from './statusLabels';

/**
 * Converts AlertStatus UPPERCASE values to canonical human-readable labels.
 * 
 * @param status - The AlertStatus enum value in UPPERCASE format (e.g., 'IN_PROGRESS', 'CLOSED_TP')
 * @returns Formatted status label (e.g., "In Progress", "Closed (True Positive)")
 * 
 * @example
 * formatStatusLabel('NEW') // Returns "New"
 * formatStatusLabel('IN_PROGRESS') // Returns "In Progress"
 * formatStatusLabel('CLOSED_TP') // Returns "Closed (True Positive)"
 */
export function formatStatusLabel(status: AlertStatus): string {
  return formatAlertStatusLabel(status);
}
