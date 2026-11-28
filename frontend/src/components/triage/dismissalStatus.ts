import type { AlertStatus } from '@/types/generated/models/AlertStatus';
import type { TriageDisposition } from '@/types/generated/models/TriageDisposition';

const DISPOSITION_TO_DISMISSAL_STATUS: Partial<Record<TriageDisposition, AlertStatus>> = {
  FALSE_POSITIVE: 'CLOSED_FP',
  BENIGN: 'CLOSED_BP',
  DUPLICATE: 'CLOSED_DUPLICATE',
};

export function getDispositionDismissalStatus(disposition: TriageDisposition): AlertStatus | undefined {
  return DISPOSITION_TO_DISMISSAL_STATUS[disposition];
}
