import { Check, CheckCircle, ChevronsUp, Copy, HelpCircle, Mail, MailOpen, XCircle } from 'lucide-react';
import type { AlertStatus } from '@/types/generated/models/AlertStatus';

const statusIcons = {
  NEW: Mail,
  IN_PROGRESS: MailOpen,
  ESCALATED: ChevronsUp,
  CLOSED_TP: Check,
  CLOSED_BP: CheckCircle,
  CLOSED_FP: XCircle,
  CLOSED_UNRESOLVED: HelpCircle,
  CLOSED_DUPLICATE: Copy,
};

export function AlertStatusIcon({ status }: { status: AlertStatus }) {
  const Icon = statusIcons[status];
  return <Icon aria-hidden="true" className="h-4 w-4 shrink-0" />;
}
