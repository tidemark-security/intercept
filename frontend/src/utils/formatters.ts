/**
 * Utility functions for formatting data values
 */

import type { AlertStatus } from '../types/generated/models/AlertStatus';

/**
 * Converts AlertStatus UPPERCASE values to human-readable Sentence Case format
 * 
 * @param status - The AlertStatus enum value in UPPERCASE format (e.g., 'IN_PROGRESS', 'CLOSED_TP')
 * @returns Formatted string in Sentence Case (e.g., "In Progress", "Closed Tp")
 * 
 * @example
 * formatStatusLabel('NEW') // Returns "New"
 * formatStatusLabel('IN_PROGRESS') // Returns "In Progress"
 * formatStatusLabel('CLOSED_TP') // Returns "Closed Tp"
 */
export function formatStatusLabel(status: AlertStatus): string {
  return status
    .toLowerCase()
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}
