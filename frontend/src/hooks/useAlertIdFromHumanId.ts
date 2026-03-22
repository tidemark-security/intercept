// Re-export from unified humanIdHelpers for backwards compatibility
import { convertAlertHumanIdToNumeric } from '@/utils/humanIdHelpers';

/**
 * Utility to convert human_id (ALT-XXXXXX) to numeric ID
 * 
 * @param humanId - The human-readable alert ID (e.g., "ALT-0000516")
 * @returns Numeric ID or null if conversion fails
 * 
 * @deprecated Use convertAlertHumanIdToNumeric from '@/utils/humanIdHelpers' instead
 */
export function convertHumanIdToNumeric(humanId: string | null | undefined): number | null {
  return convertAlertHumanIdToNumeric(humanId);
}
