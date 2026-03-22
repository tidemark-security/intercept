/**
 * Human ID Helpers
 * 
 * Unified utilities for converting between human-readable IDs (CAS-00123, ALT-00456, TSK-00789)
 * and numeric IDs. These utilities are used across Case, Alert, and Task entities.
 */

/**
 * Generic converter for human-readable IDs to numeric IDs
 * 
 * @param humanId - Human-readable ID (e.g., "CAS-00123", "ALT-00456", "TSK-00789")
 * @param prefix - Expected prefix (e.g., "CAS-", "ALT-", "TSK-")
 * @returns Numeric ID or null if invalid format
 * 
 * @example
 * ```ts
 * convertHumanIdToNumeric("CAS-00123", "CAS-") // Returns: 123
 * convertHumanIdToNumeric("ALT-00001", "ALT-") // Returns: 1
 * convertHumanIdToNumeric("invalid", "CAS-")  // Returns: null
 * ```
 */
export function convertHumanIdToNumeric(
  humanId: string | null | undefined,
  prefix: string
): number | null {
  if (!humanId) {
    return null;
  }
  
  // Create a regex pattern for the prefix followed by digits
  const escapedPrefix = prefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = new RegExp(`^${escapedPrefix}(\\d+)$`, 'i');
  const match = humanId.match(pattern);
  
  if (!match) {
    return null;
  }
  
  const numericId = parseInt(match[1], 10);
  return isNaN(numericId) ? null : numericId;
}

/**
 * Generic converter for numeric IDs to human-readable IDs
 * 
 * @param numericId - Numeric ID (e.g., 123)
 * @param prefix - Prefix to use (e.g., "CAS-", "ALT-", "TSK-")
 * @param padLength - Length to zero-pad the number (default: 7)
 * @returns Human-readable ID (e.g., "CAS-0000123")
 * 
 * @example
 * ```ts
 * convertNumericToHumanId(123, "CAS-") // Returns: "CAS-0000123"
 * convertNumericToHumanId(1, "ALT-")   // Returns: "ALT-0000001"
 * ```
 */
export function convertNumericToHumanId(
  numericId: number,
  prefix: string,
  padLength: number = 7
): string {
  return `${prefix}${numericId.toString().padStart(padLength, '0')}`;
}

// ============================================================================
// Entity-specific convenience functions
// ============================================================================

/**
 * Convert a human-readable case ID to a numeric ID
 * @param humanId - Case ID in format "CAS-00123"
 * @returns Numeric ID (e.g., 123) or null if invalid format
 */
export const convertCaseHumanIdToNumeric = (humanId: string | null | undefined): number | null =>
  convertHumanIdToNumeric(humanId, 'CAS-');

/**
 * Convert a human-readable alert ID to a numeric ID
 * @param humanId - Alert ID in format "ALT-00123"
 * @returns Numeric ID (e.g., 123) or null if invalid format
 */
export const convertAlertHumanIdToNumeric = (humanId: string | null | undefined): number | null =>
  convertHumanIdToNumeric(humanId, 'ALT-');

/**
 * Convert a human-readable task ID to a numeric ID
 * @param humanId - Task ID in format "TSK-00123"
 * @returns Numeric ID (e.g., 123) or null if invalid format
 */
export const convertTaskHumanIdToNumeric = (humanId: string | null | undefined): number | null =>
  convertHumanIdToNumeric(humanId, 'TSK-');

/**
 * Convert a numeric case ID to a human-readable ID
 * @param numericId - Numeric case ID (e.g., 123)
 * @returns Human-readable ID in format "CAS-0000123"
 */
export const convertCaseNumericToHumanId = (numericId: number): string =>
  convertNumericToHumanId(numericId, 'CAS-');

/**
 * Convert a numeric alert ID to a human-readable ID
 * @param numericId - Numeric alert ID (e.g., 123)
 * @returns Human-readable ID in format "ALT-0000123"
 */
export const convertAlertNumericToHumanId = (numericId: number): string =>
  convertNumericToHumanId(numericId, 'ALT-');

/**
 * Convert a numeric task ID to a human-readable ID
 * @param numericId - Numeric task ID (e.g., 123)
 * @returns Human-readable ID in format "TSK-0000123"
 */
export const convertTaskNumericToHumanId = (numericId: number): string =>
  convertNumericToHumanId(numericId, 'TSK-');
