// Re-export from unified humanIdHelpers for backwards compatibility
import {
  convertCaseHumanIdToNumeric,
  convertCaseNumericToHumanId,
  convertAlertNumericToHumanId,
} from './humanIdHelpers';

/**
 * Convert a human-readable case ID to a numeric ID
 * @param humanId - Case ID in format "CAS-00123"
 * @returns Numeric ID (e.g., 123) or null if invalid format
 * 
 * @deprecated Use convertCaseHumanIdToNumeric from '@/utils/humanIdHelpers' instead
 */
export function convertHumanIdToNumeric(humanId: string): number | null {
  return convertCaseHumanIdToNumeric(humanId);
}

/**
 * Convert a numeric case ID to a human-readable ID
 * @param numericId - Numeric case ID (e.g., 123)
 * @returns Human-readable ID in format "CAS-0000123"
 * 
 * @deprecated Use convertCaseNumericToHumanId from '@/utils/humanIdHelpers' instead
 */
export function convertNumericToHumanId(numericId: number): string {
  return convertCaseNumericToHumanId(numericId);
}

/**
 * Convert a numeric alert ID to a human-readable ID
 * @param numericId - Numeric alert ID (e.g., 123)
 * @returns Human-readable ID in format "ALT-0000123"
 * 
 * @deprecated Use convertAlertNumericToHumanId from '@/utils/humanIdHelpers' instead
 */
export function convertNumericToAlertId(numericId: number): string {
  return convertAlertNumericToHumanId(numericId);
}
