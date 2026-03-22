import React from 'react';

import { Badge } from '@/components/data-display/Badge';
import { Button } from '@/components/buttons/Button';
import { IconWithBackground } from '@/components/misc/IconWithBackground';

import { Sparkles } from 'lucide-react';

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
    <div className="flex w-full flex-col items-start gap-4 rounded-md border border-dashed border-neutral-border bg-neutral-50 px-6 py-6">
      <div className="flex w-full items-center gap-3">
        <IconWithBackground
          variant="neutral"
          size="medium"
          icon={<Sparkles />}
        />
        <div className="flex flex-1 flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className="text-body-bold font-body-bold text-default-font">
              AI Triage Available
            </span>
            <Badge variant="neutral">Not Requested</Badge>
          </div>
          <span className="text-caption font-caption text-subtext-color">
            Request AI-powered analysis to get disposition recommendations and suggested actions.
          </span>
        </div>
      </div>
      
      <Button
        variant="brand-primary"
        onClick={onRequestTriage}
        disabled={isEnqueuing}
        loading={isEnqueuing}
        icon={<Sparkles className="h-4 w-4" />}
      >
        Request AI Triage
      </Button>
    </div>
  );
}
