import React, { useEffect, useMemo, useRef, useState } from 'react';

import { Badge } from '@/components/data-display/Badge';
import { RelativeTime } from '@/components/data-display/RelativeTime';
import { Button } from '@/components/buttons/Button';
import { Dialog } from '@/components/overlays/Dialog';
import { IconButton } from '@/components/buttons/IconButton';
import { Priority } from '@/components/misc/Priority';
import { Progress } from '@/components/feedback/Progress';
import { Select } from '@/components/forms/Select';
import { State } from '@/components/misc/State';
import { TextArea } from '@/components/forms/TextArea';
import { useTheme } from '@/contexts/ThemeContext';
import { cn } from '@/utils/cn';
import type { TriageRecommendationRead } from '@/types/generated/models/TriageRecommendationRead';
import type { AcceptRecommendationRequest } from '@/types/generated/models/AcceptRecommendationRequest';
import type { RejectionCategory } from '@/types/generated/models/RejectionCategory';
import { alertStatusToUIState, priorityToUIPriority } from '@/utils/statusHelpers';
import type { AlertStatus } from '@/types/generated/models/AlertStatus';
import type { Priority as PriorityType } from '@/types/generated/models/Priority';
import { ReasoningText } from './ReasoningText';

import { AlertCircle, ArrowRight, Check, ChevronDown, ChevronUp, Loader2, RefreshCw, Sparkles, Tag, TriangleAlert, X } from 'lucide-react';
// Helper to format disposition for display
function formatDisposition(disposition: string): string {
  return disposition
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// Helper to format confidence as percentage
function formatConfidence(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
}

// Map disposition to badge variant
function getDispositionVariant(disposition: string): 'error' | 'success' | 'warning' | 'neutral' | 'brand' {
  switch (disposition) {
    case 'TRUE_POSITIVE':
      return 'error';
    case 'FALSE_POSITIVE':
      return 'success';
    case 'BENIGN':
      return 'success';
    case 'NEEDS_INVESTIGATION':
      return 'warning';
    case 'DUPLICATE':
      return 'neutral';
    default:
      return 'neutral';
  }
}

// Map status to badge variant  
function getStatusVariant(status: string): 'error' | 'success' | 'warning' | 'neutral' | 'brand' {
  switch (status) {
    case 'ACCEPTED':
      return 'success';
    case 'REJECTED':
      return 'error';
    case 'FAILED':
      return 'error';
    case 'SUPERSEDED':
      return 'neutral';
    case 'QUEUED':
      return 'brand';
    default:
      return 'brand';
  }
}

// Dismiss statuses that indicate alert should be closed
const DISMISS_STATUSES = ['CLOSED_FP', 'CLOSED_BP', 'CLOSED_DUPLICATE', 'CLOSED_UNRESOLVED'];

// Disposition-to-status mapping for dismiss/close outcomes
const DISPOSITION_TO_RECOMMENDED_STATUS: Record<string, string> = {
  FALSE_POSITIVE: 'CLOSED_FP',
  BENIGN: 'CLOSED_BP',
  DUPLICATE: 'CLOSED_DUPLICATE',
};

function getInferredSuggestedStatus(recommendation: TriageRecommendationRead): string | undefined {
  return recommendation.suggested_status || DISPOSITION_TO_RECOMMENDED_STATUS[recommendation.disposition];
}

// Get inferred recommended action based on recommendation data
function getRecommendedAction(recommendation: TriageRecommendationRead): {
  text: string;
  variant: 'escalate' | 'dismiss' | 'manual';
} {
  const inferredSuggestedStatus = getInferredSuggestedStatus(recommendation);

  if (inferredSuggestedStatus && DISMISS_STATUSES.includes(inferredSuggestedStatus)) {
    return { text: 'Dismiss alert', variant: 'dismiss' };
  }
  if (recommendation.request_escalate_to_case) {
    return { text: 'Escalate to case and investigate', variant: 'escalate' };
  }
  return { text: 'Low confidence - Escalate to case and investigate', variant: 'manual' };
}

// Get status label for badge display
function getStatusLabel(status: string): string {
  switch (status) {
    case 'PENDING':
      return 'Pending Review';
    case 'ACCEPTED':
      return 'Accepted';
    case 'REJECTED':
      return 'Rejected';
    case 'SUPERSEDED':
      return 'Superseded';
    default:
      return status;
  }
}

// Rejection category options for dropdown
const REJECTION_CATEGORY_OPTIONS: { value: RejectionCategory; label: string }[] = [
  { value: 'INCORRECT_DISPOSITION', label: 'Incorrect Disposition' },
  { value: 'WRONG_SUGGESTED_STATUS', label: 'Wrong Suggested Status' },
  { value: 'WRONG_PRIORITY', label: 'Wrong Priority' },
  { value: 'MISSING_CONTEXT', label: 'Missing Context' },
  { value: 'INCOMPLETE_ANALYSIS', label: 'Incomplete Analysis' },
  { value: 'PREFER_MANUAL_REVIEW', label: 'Prefer Manual Review' },
  { value: 'FALSE_REASONING', label: 'False Reasoning' },
  { value: 'OTHER', label: 'Other' },
];

interface TriageRecommendationCardProps {
  recommendation: TriageRecommendationRead;
  onAccept: (options: AcceptRecommendationRequest) => void;
  onReject: (category: RejectionCategory, reason?: string) => void;
  onRetry?: () => void;
  onNavigateToCase?: (caseHumanId: string) => void;
  isAccepting?: boolean;
  isRejecting?: boolean;
  isRetrying?: boolean;
  defaultExpanded?: boolean;
}

export function TriageRecommendationCard({
  recommendation,
  onAccept,
  onReject,
  onRetry,
  onNavigateToCase,
  isAccepting = false,
  isRejecting = false,
  isRetrying = false,
  defaultExpanded = false,
}: TriageRecommendationCardProps) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';
  const brandTextClass = isDarkTheme ? 'text-brand-primary' : 'text-brand-1000';

  const isPending = recommendation.status === 'PENDING';
  const isQueued = recommendation.status === 'QUEUED';
  const isFailed = recommendation.status === 'FAILED';
  const isReviewed = ['ACCEPTED', 'REJECTED', 'SUPERSEDED'].includes(recommendation.status);
  
  // Collapse/expand state - reviewed recommendations start collapsed by default
  const [isExpanded, setIsExpanded] = useState(isReviewed ? defaultExpanded : true);
  
  // Rejection dialog state
  const [showRejectDialog, setShowRejectDialog] = useState(false);
  const [rejectionCategory, setRejectionCategory] = useState<RejectionCategory | ''>('');
  const [rejectionReason, setRejectionReason] = useState('');
  const previousRecommendationStatusRef = useRef(recommendation.status);

  const inferredSuggestedStatus = useMemo(() => {
    return getInferredSuggestedStatus(recommendation);
  }, [recommendation]);
  
  // Calculate if there are any suggested changes
  const hasSuggestedChanges = useMemo(() => {
    return !!(
      inferredSuggestedStatus ||
      recommendation.suggested_priority ||
      recommendation.suggested_assignee ||
      (recommendation.suggested_tags_add && recommendation.suggested_tags_add.length > 0) ||
      (recommendation.suggested_tags_remove && recommendation.suggested_tags_remove.length > 0)
    );
  }, [
    inferredSuggestedStatus,
    recommendation.suggested_priority,
    recommendation.suggested_assignee,
    recommendation.suggested_tags_add,
    recommendation.suggested_tags_remove,
  ]);
  
  const handleAccept = () => {
    onAccept({
      apply_status: true,
      apply_priority: true,
      apply_assignee: true,
      apply_tags: true,
    });
  };
  
  // Get inferred action for display
  const recommendedAction = useMemo(() => getRecommendedAction(recommendation), [recommendation]);
  
  const handleRejectConfirm = () => {
    if (rejectionCategory && (rejectionCategory !== 'OTHER' || rejectionReason.trim())) {
      onReject(rejectionCategory, rejectionReason.trim() || undefined);
      setShowRejectDialog(false);
      setRejectionCategory('');
      setRejectionReason('');
    }
  };
  
  const handleRejectCancel = () => {
    setShowRejectDialog(false);
    setRejectionCategory('');
    setRejectionReason('');
  };

  useEffect(() => {
    const previousStatus = previousRecommendationStatusRef.current;
    if (previousStatus !== recommendation.status && recommendation.status === 'ACCEPTED') {
      setIsExpanded(false);
    }
    previousRecommendationStatusRef.current = recommendation.status;
  }, [recommendation.status]);

  // QUEUED state - show processing indicator
  if (isQueued) {
    return (
      <div
        className={`flex w-full flex-col items-start gap-4 rounded-md border border-solid ${
          isDarkTheme ? 'border-brand-primary bg-brand-900' : 'border-brand-800 bg-brand-primary'
        } px-6 py-6`}
      >
        <div className="flex w-full items-center gap-3">
          <div
            className={cn(
              "flex h-10 w-10 items-center justify-center",
              isDarkTheme ? "bg-brand-800" : "bg-brand-100"
            )}
          >
            <Loader2 className={cn("h-5 w-5 animate-spin", brandTextClass)} />
          </div>
          <div className="flex flex-1 flex-col gap-1">
            <div className="flex items-center gap-2">
              <span className={cn("text-body-bold font-body-bold", brandTextClass)}>
                AI Triage In Progress
              </span>
              <Badge variant="brand">Processing</Badge>
            </div>
            <span className={cn("text-caption font-caption", brandTextClass)}>
              Analyzing alert details and generating recommendations...
            </span>
          </div>
        </div>
        <div className={cn("flex w-full items-center gap-2 text-caption", brandTextClass)}>
          <Sparkles className="h-4 w-4" />
          <span>This may take a few moments. The recommendation will appear automatically when ready.</span>
        </div>
      </div>
    );
  }

  // FAILED state - show error with retry option
  if (isFailed) {
    return (
      <div className="flex w-full flex-col items-start gap-4 rounded-md border border-solid border-error-200 bg-error-50 px-6 py-6">
        <div className="flex w-full items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-error-100">
            <TriangleAlert className="h-5 w-5 text-error-600" />
          </div>
          <div className="flex flex-1 flex-col gap-1">
            <div className="flex items-center gap-2">
              <span className="text-body-bold font-body-bold text-error-700">
                AI Triage Failed
              </span>
              <Badge variant="error">Failed</Badge>
            </div>
            <span className="text-caption font-caption text-error-600">
              Unable to generate triage recommendation
            </span>
          </div>
        </div>
        
        {recommendation.error_message && (
          <div className="flex w-full flex-col gap-1 rounded-md bg-error-100 p-3">
            <span className="text-caption-bold font-caption-bold text-error-700">Error Details</span>
            <span className="text-caption font-caption text-error-700">
              {recommendation.error_message}
            </span>
          </div>
        )}
        
        {onRetry && (
          <Button
            variant="neutral-secondary"
            onClick={onRetry}
            disabled={isRetrying}
            loading={isRetrying}
            icon={<RefreshCw className="h-4 w-4" />}
          >
            Retry AI Triage
          </Button>
        )}
      </div>
    );
  }

  // Collapsed view for reviewed (accepted/rejected/superseded) recommendations
  if (isReviewed && !isExpanded) {
    return (
      <div
        className={`flex w-full items-center gap-4 rounded-md border border-solid ${
          isDarkTheme ? 'border-neutral-100' : 'border-neutral-600'
        } bg-neutral-50 px-4 py-3 shadow-sm flex-wrap`}
      >
        <div className="flex items-center gap-3">
          <Sparkles className="h-5 w-5 text-subtext-color" />
          <span className="text-heading-3 font-heading-3 text-subtext-color">
            AI Triage Recommendation
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Badge 
            variant={getStatusVariant(recommendation.status)} 
            icon={recommendation.status === 'ACCEPTED' ? <Check className="h-3 w-3" /> : recommendation.status === 'REJECTED' ? <X className="h-3 w-3" /> : undefined}
          >
            {getStatusLabel(recommendation.status)}
          </Badge>
        </div>
        <div className="hidden sm:flex h-4 w-px flex-none flex-col items-center gap-2 bg-neutral-border" />
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-body font-body text-subtext-color">
              Confidence:
            </span>
            <span className="text-body-bold font-body-bold text-default-font">
              {formatConfidence(recommendation.confidence)}
            </span>
          </div>
          <Badge 
            variant={getDispositionVariant(recommendation.disposition)} 
            icon={recommendation.disposition === 'TRUE_POSITIVE' ? <TriangleAlert className="h-3 w-3" /> : undefined}
          >
            {formatDisposition(recommendation.disposition).toUpperCase()}
          </Badge>
        </div>
        <div className="flex grow shrink-0 basis-0 items-center justify-end gap-2">
          <span className="text-caption font-caption text-subtext-color">
            {recommendation.status === 'ACCEPTED' && recommendation.reviewed_by && (
              <>Accepted by {recommendation.reviewed_by}</>
            )}
            {recommendation.status === 'REJECTED' && recommendation.reviewed_by && (
              <>Rejected by {recommendation.reviewed_by}</>
            )}
            {recommendation.status === 'SUPERSEDED' && (
              <>Superseded</>
            )}
            {recommendation.reviewed_at && (
              <>
                {' • '}
                <RelativeTime value={recommendation.reviewed_at} />
              </>
            )}
          </span>
          <IconButton
            variant="neutral-tertiary"
            icon={<ChevronDown className="h-4 w-4" />}
            onClick={() => setIsExpanded(true)}
          />
        </div>
      </div>
    );
  }

  return (
    <div
      className={`flex w-full flex-col items-start gap-6 border border-solid ${
        isDarkTheme ? 'border-neutral-100' : 'border-neutral-400'
      } bg-default-background px-6 py-6`}
    >
      {/* Header */}
      <div className="flex w-full flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-default-font" />
          <span className="text-heading-3 font-heading-3 text-default-font">
            AI Triage Recommendation
          </span>
        </div>
        <Badge variant={getStatusVariant(recommendation.status)}>
          {getStatusLabel(recommendation.status)}
        </Badge>
        {/* Collapse button for reviewed recommendations */}
        {isReviewed && (
          <div className="flex grow shrink-0 basis-0 items-center justify-end">
            <IconButton
              variant="neutral-tertiary"
              icon={<ChevronUp className="h-4 w-4" />}
              onClick={() => setIsExpanded(false)}
            />
          </div>
        )}
      </div>
      
      {/* Confidence & Disposition Row */}
      <div className="flex w-full flex-wrap items-center gap-6">
        <div className="flex min-w-[240px] grow shrink-0 basis-0 flex-col items-start gap-2">
          <span className="text-body-bold font-body-bold text-subtext-color">
            Confidence
          </span>
          <div className="flex w-full items-center gap-3">
            <Progress value={Math.round(recommendation.confidence * 100)} />
            <span
              className={cn(
                'text-heading-2 font-heading-2',
                brandTextClass
              )}
            >
              {formatConfidence(recommendation.confidence)}
            </span>
          </div>
        </div>
        <div className="flex flex-col items-start gap-2">
          <span className="text-body-bold font-body-bold text-subtext-color">
            Disposition
          </span>
          <Badge 
            variant={getDispositionVariant(recommendation.disposition)} 
            icon={recommendation.disposition === 'TRUE_POSITIVE' ? <TriangleAlert className="h-3 w-3" /> : undefined}
          >
            {formatDisposition(recommendation.disposition).toUpperCase()}
          </Badge>
        </div>
      </div>
      
      {/* Recommended Action Banner */}
      <div className="flex w-full flex-col items-start gap-2">
        <span className="text-body-bold font-body-bold text-subtext-color">
          Recommended Action
        </span>
        <div className={`flex w-full items-center gap-3 px-4 py-3 border border-solid ${
          recommendedAction.variant === 'escalate' 
            ? `border-error-500 ${isDarkTheme ? 'bg-error-1000' : 'bg-error-100'}` 
            : recommendedAction.variant === 'dismiss'
            ? `border-success-500 ${isDarkTheme ? 'bg-success-1000' : 'bg-success-100'}`
            : `border-warning-500 ${isDarkTheme ? 'bg-warning-1000' : 'bg-warning-100'}`
        }`}>
          {recommendedAction.variant === 'escalate' && (
            <TriangleAlert className="h-6 w-6 text-error-600 flex-shrink-0" />
          )}
          {recommendedAction.variant === 'dismiss' && (
            <Check className={cn("h-6 w-6 flex-shrink-0", isDarkTheme ? "text-success-600" : "text-success-800")} />
          )}
          {recommendedAction.variant === 'manual' && (
            <AlertCircle className="h-6 w-6 text-warning-600 flex-shrink-0" />
          )}
          <span className="grow shrink-0 basis-0 text-heading-3 font-heading-3 text-default-font">
            {recommendedAction.text}
          </span>
        </div>
      </div>
      
      {/* Divider */}
      <div className="flex h-px w-full flex-none bg-neutral-border" />
      
      {/* Reasoning Section */}
      {recommendation.reasoning_bullets && recommendation.reasoning_bullets.length > 0 && (
        <>
          <div className="flex w-full flex-col items-start gap-4">
            <span className="text-heading-3 font-heading-3 text-default-font">
              Reasoning
            </span>
            <div className="flex w-full flex-col items-start gap-3">
              {recommendation.reasoning_bullets.map((bullet, idx) => (
                <div key={idx} className="flex items-start gap-3">
                  <ArrowRight className={cn("h-4 w-4 flex-shrink-0 mt-0.5", brandTextClass)} />
                  <ReasoningText 
                    text={bullet} 
                    className="grow shrink-0 basis-0 text-body font-body text-default-font"
                  />
                </div>
              ))}
            </div>
          </div>
          <div className="flex h-px w-full flex-none bg-neutral-border" />
        </>
      )}
      
      {/* Recommended Changes Section */}
      {hasSuggestedChanges && (
        <>
          <div className="flex w-full flex-col items-start gap-4">
            <span className="text-heading-3 font-heading-3 text-default-font">
              Recommended Changes
            </span>
            <div className="flex w-full flex-wrap items-start gap-4">
              {inferredSuggestedStatus && (
                <div className="flex min-w-[160px] grow shrink-0 basis-0 flex-col items-start gap-2">
                  <span className="text-caption-bold font-caption-bold text-subtext-color">
                    Status
                  </span>
                  <State 
                    state={alertStatusToUIState(inferredSuggestedStatus as AlertStatus)} 
                    variant="small" 
                  />
                </div>
              )}
              {recommendation.suggested_priority && (
                <div className="flex min-w-[160px] grow shrink-0 basis-0 flex-col items-start gap-2">
                  <span className="text-caption-bold font-caption-bold text-subtext-color">
                    Priority
                  </span>
                  <Priority 
                    priority={priorityToUIPriority(recommendation.suggested_priority as PriorityType)} 
                  />
                </div>
              )}
              {recommendation.suggested_assignee && (
                <div className="flex min-w-[160px] grow shrink-0 basis-0 flex-col items-start gap-2">
                  <span className="text-caption-bold font-caption-bold text-subtext-color">
                    Assignee
                  </span>
                  <span className="text-body-bold font-body-bold text-default-font">
                    {recommendation.suggested_assignee}
                  </span>
                </div>
              )}
              {recommendation.suggested_tags_add && recommendation.suggested_tags_add.length > 0 && (
                <div className="flex min-w-[160px] grow shrink-0 basis-0 flex-col items-start gap-2">
                  <span className="text-caption-bold font-caption-bold text-subtext-color">
                    Add Tags
                  </span>
                  <div className="flex flex-wrap items-center gap-2">
                    {recommendation.suggested_tags_add.map((tag, idx) => (
                      <Badge key={idx} variant="neutral" icon={<Tag className="h-3 w-3" />}>
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
              {recommendation.suggested_tags_remove && recommendation.suggested_tags_remove.length > 0 && (
                <div className="flex min-w-[160px] grow shrink-0 basis-0 flex-col items-start gap-2">
                  <span className="text-caption-bold font-caption-bold text-subtext-color">
                    Remove Tags
                  </span>
                  <div className="flex flex-wrap items-center gap-2">
                    {recommendation.suggested_tags_remove.map((tag, idx) => (
                      <Badge key={idx} variant="error" icon={<Tag className="h-3 w-3" />}>
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
          <div className="flex h-px w-full flex-none bg-neutral-border" />
        </>
      )}
      
      {/* Recommended Tasks Section */}
      {recommendation.recommended_actions && recommendation.recommended_actions.length > 0 && (
        <>
          <div className="flex w-full flex-col items-start gap-4">
            <span className="text-heading-3 font-heading-3 text-default-font">
              Recommended Tasks
            </span>
            <div className="flex w-full flex-col items-start gap-3">
              {recommendation.recommended_actions.map((action, idx) => (
                <div key={idx} className="flex items-start gap-3">
                  <ArrowRight className={cn("h-4 w-4 flex-shrink-0 mt-0.5", brandTextClass)} />
                  <span className="grow shrink-0 basis-0 text-body font-body text-default-font">
                    {typeof action === 'string' ? action : action.title}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
      

      
      {/* Rejection Reason (Rejected only) */}
      {recommendation.status === 'REJECTED' && recommendation.rejection_reason && (
        <>
          <div className="flex w-full flex-col gap-2 rounded-md bg-error-50 p-3">
            <span className="text-caption-bold font-caption-bold text-error-700">
              Rejection Reason
            </span>
            <span className="text-body font-body text-error-700">
              {recommendation.rejection_reason}
            </span>
          </div>
          <div className="flex h-px w-full flex-none bg-neutral-border" />
        </>
      )}
      
      {/* Superseded Notice */}
      {recommendation.status === 'SUPERSEDED' && (
        <>
          <div className="flex w-full items-center gap-2 rounded-md bg-neutral-100 p-3">
            <span className="text-caption font-caption text-subtext-color">
              This recommendation has been superseded by a newer one.
            </span>
          </div>
          <div className="flex h-px w-full flex-none bg-neutral-border" />
        </>
      )}
      
      {/* Action Buttons (Pending only) */}
      {isPending && (
        <div className="flex w-full flex-wrap items-center justify-end gap-3">
          <Button
            variant="neutral-secondary"
            icon={<X className="h-4 w-4" />}
            onClick={() => setShowRejectDialog(true)}
            disabled={isRejecting || isAccepting}
            loading={isRejecting}
          >
            Reject
          </Button>
          <Button
            variant="brand-primary"
            icon={<Check className="h-4 w-4" />}
            onClick={handleAccept}
            disabled={isAccepting || isRejecting}
            loading={isAccepting}
          >
            Accept Recommendation
          </Button>
        </div>
      )}
      
      {/* Rejection Dialog */}
      <Dialog open={showRejectDialog} onOpenChange={setShowRejectDialog}>
        <Dialog.Content className="p-6">
          <div className="flex flex-col gap-4 w-[400px]">
            <div className="flex flex-col gap-1">
              <span className="text-heading-3 font-heading-3 text-default-font">
                Reject Recommendation
              </span>
              <span className="text-body font-body text-subtext-color">
                Select the reason for rejecting this AI triage recommendation.
              </span>
            </div>
            
            <Select
              label="Rejection Category"
              helpText="Required"
              value={rejectionCategory}
              onValueChange={(value) => setRejectionCategory(value as RejectionCategory)}
              placeholder="Select a category..."
            >
              {REJECTION_CATEGORY_OPTIONS.map((option) => (
                <Select.Item key={option.value} value={option.value}>
                  {option.label}
                </Select.Item>
              ))}
            </Select>
            
            <TextArea
              label="Additional Details"
              helpText={rejectionCategory === 'OTHER' ? 'Required for "Other" category' : 'Optional'}
            >
              <TextArea.Input
                placeholder="Provide additional context for the rejection..."
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
              />
            </TextArea>
            
            <div className="flex items-center justify-end gap-3">
              <Button
                variant="neutral-secondary"
                size="small"
                onClick={handleRejectCancel}
              >
                Cancel
              </Button>
              <Button
                variant="destructive-primary"
                size="small"
                onClick={handleRejectConfirm}
                disabled={!rejectionCategory || (rejectionCategory === 'OTHER' && !rejectionReason.trim())}
              >
                Reject Recommendation
              </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog>
    </div>
  );
}
