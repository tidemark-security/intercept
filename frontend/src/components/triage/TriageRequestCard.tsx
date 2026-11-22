import { Sparkles } from 'lucide-react';
import { TriageStatusCard } from './TriageStatusCard';

interface TriageRequestCardProps {
  /** Callback to trigger AI triage */
  onRequestTriage: () => void;
  /** Whether the enqueue request is in progress */
  isEnqueuing?: boolean;
}

/**
 * Card displayed when no triage recommendation exists for an alert.
 * Allows the user to manually trigger AI triage.
 * 
 * This component should only be rendered when:
 * 1. AI triage is enabled (feature flag: ai_triage_enabled)
 * 2. No triage recommendation exists for the alert
 */
export function TriageRequestCard({
  onRequestTriage,
  isEnqueuing = false,
}: TriageRequestCardProps) {
  return (
    <TriageStatusCard
      title="AI Triage Available"
      description="Get a suggested disposition and next steps."
      icon={<Sparkles />}
      action={{ label: 'Request AI Triage', onClick: onRequestTriage, busy: isEnqueuing, icon: <Sparkles /> }}
    />
  );
}
