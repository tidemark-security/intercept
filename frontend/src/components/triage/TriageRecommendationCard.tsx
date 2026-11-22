import { useEffect, useId, useMemo, useState, type ReactNode } from 'react';
import { Accordion } from '@tidemark-security/ux';

import { Badge } from '@/components/data-display/Badge';
import { RelativeTime } from '@/components/data-display/RelativeTime';
import { InlineMarkdown } from '@/components/data-display/InlineMarkdown';
import { Button } from '@/components/buttons/Button';
import { IconButton } from '@/components/buttons/IconButton';
import { Select } from '@/components/forms/Select';
import { Priority } from '@/components/misc/Priority';
import { State } from '@/components/misc/State';
import { useTheme } from '@/contexts/ThemeContext';
import { useAlertPanelExpansion } from '@/hooks/useAlertPanelExpansion';
import { useCaseRunbooks } from '@/hooks/useCaseRunbooks';
import { cn } from '@/utils/cn';
import { IconWrapper } from '@/utils/IconWrapper';
import type { TriageRecommendationRead } from '@/types/generated/models/TriageRecommendationRead';
import type { AcceptRecommendationRequest } from '@/types/generated/models/AcceptRecommendationRequest';
import type { RejectionCategory } from '@/types/generated/models/RejectionCategory';
import { alertStatusToUIState, priorityToUIPriority } from '@/utils/statusHelpers';
import type { AlertStatus } from '@/types/generated/models/AlertStatus';
import { ReasoningText } from './ReasoningText';
import { TriageRejectionDialog } from './TriageRejectionDialog';
import { TriageStatusCard } from './TriageStatusCard';
import styles from './TriageRecommendationCard.module.css';

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

function TriageDetailRow({
  label,
  preview,
  hint,
  children,
}: {
  label: string;
  preview: ReactNode;
  hint?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);

  return (
    <Accordion
      open={open}
      onOpenChange={setOpen}
      className="min-w-0 rounded-none border-t border-solid border-neutral-border [&>button]:text-left [&>button:hover]:bg-neutral-50 [&>button:focus-visible]:outline [&>button:focus-visible]:outline-2 [&>button:focus-visible]:outline-focus-border [&>button:focus-visible]:-outline-offset-2"
      trigger={(
        <span className={cn(styles.disclosure, 'grid w-full min-w-0 items-center gap-x-3 gap-y-1 px-1 py-2')}>
          <span className="text-heading-3 font-heading-3 text-default-font">{label}</span>
          {!open && <span className={cn(styles.preview, 'min-w-0')}>{preview}</span>}
          <span className={cn(styles.toggle, 'flex shrink-0 items-center justify-end gap-2 text-caption font-caption text-subtext-color')}>
            {!open && hint && <span>{hint}</span>}
            <Accordion.Chevron className="h-4 w-4" aria-hidden="true" />
          </span>
        </span>
      )}
    >
      <div className="w-full min-w-0 px-1 pb-3">{children}</div>
    </Accordion>
  );
}

function TriageDetailList({ children }: { children: ReactNode }) {
  return (
    <ul className="flex min-w-0 flex-col gap-2 text-body font-body text-default-font [overflow-wrap:anywhere]">
      {children}
    </ul>
  );
}

function TriageDetailItem({ children }: { children: ReactNode }) {
  return (
    <li className="flex min-w-0 items-start gap-2">
      <IconWrapper className="mt-0.5 h-4 w-4 shrink-0 text-subtext-color" aria-hidden="true">
        <ArrowRight />
      </IconWrapper>
      {children}
    </li>
  );
}

function getTaskTitle(action: unknown): string {
  if (typeof action === 'string') return action;
  if (action && typeof action === 'object' && 'title' in action && typeof action.title === 'string') {
    return action.title;
  }
  return '';
}

interface TriageRecommendationCardProps {
  recommendation: TriageRecommendationRead;
  onAccept: (options: AcceptRecommendationRequest) => void;
  onReject: (category: RejectionCategory, reason?: string) => void;
  onRetry?: () => void;
  onNavigateToCase?: (caseHumanId: string) => void;
  acceptError?: string | null;
  isAccepting?: boolean;
  isRejecting?: boolean;
  isRetrying?: boolean;
  defaultExpanded?: boolean;
  canReview?: boolean;
}

export function TriageRecommendationCard({
  recommendation,
  onAccept,
  onReject,
  onRetry,
  acceptError,
  isAccepting = false,
  isRejecting = false,
  isRetrying = false,
  defaultExpanded = false,
  canReview = true,
}: TriageRecommendationCardProps) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';
  const brandTextClass = isDarkTheme ? 'text-brand-primary' : 'text-brand-1000';

  const isPending = recommendation.status === 'PENDING';
  const isQueued = recommendation.status === 'QUEUED';
  const isFailed = recommendation.status === 'FAILED';
  const isReviewed = ['ACCEPTED', 'REJECTED', 'SUPERSEDED'].includes(recommendation.status);
  
  const [isExpanded, setIsExpanded] = useAlertPanelExpansion('triage-recommendation', !isReviewed || defaultExpanded);
  const contentId = useId();
  const [replacementRunbookId, setReplacementRunbookId] = useState<string>('');
  
  // Rejection dialog state
  const [showRejectDialog, setShowRejectDialog] = useState(false);

  const inferredSuggestedStatus = useMemo(() => {
    return getInferredSuggestedStatus(recommendation);
  }, [recommendation]);
  
  const reasons = recommendation.reasoning_bullets ?? [];
  const tasks = (recommendation.recommended_actions ?? []).map(getTaskTitle).filter(Boolean);
  const tagsToAdd = recommendation.suggested_tags_add ?? [];
  const tagsToRemove = recommendation.suggested_tags_remove ?? [];
  const suggestedState = inferredSuggestedStatus ? alertStatusToUIState(inferredSuggestedStatus as AlertStatus) : null;
  const suggestedPriority = recommendation.suggested_priority ? priorityToUIPriority(recommendation.suggested_priority) : null;
  const hasSuggestedChanges = suggestedState || suggestedPriority || recommendation.suggested_assignee
    || tagsToAdd.length > 0 || tagsToRemove.length > 0;
  
  const buildAcceptOptions = (patch: Partial<AcceptRecommendationRequest> = {}): AcceptRecommendationRequest => ({
      apply_status: true,
      apply_priority: true,
      apply_assignee: true,
      apply_tags: true,
      ...patch,
  });

  const handleAccept = () => {
    onAccept(buildAcceptOptions());
  };
  
  // Get inferred action for display
  const recommendedAction = useMemo(() => getRecommendedAction(recommendation), [recommendation]);
  const contextIndicator = recommendation.applied_context_entries?.length ? (
    <span className="inline-flex items-center gap-1.5 text-caption font-caption text-subtext-color" title="Analyst context included in this triage">
      <Check aria-hidden="true" className={cn("h-4 w-4 shrink-0", brandTextClass)} />
      Context included
    </span>
  ) : null;
  const shouldShowRunbookRecovery = Boolean(
    isPending &&
    canReview &&
    recommendation.request_escalate_to_case &&
    acceptError &&
    acceptError.toLowerCase().includes('runbook')
  );
  const { data: publishedRunbooksData, isLoading: isLoadingRunbooks } = useCaseRunbooks(['PUBLISHED'], null);
  const publishedRunbooks = useMemo(() => publishedRunbooksData?.items ?? [], [publishedRunbooksData?.items]);
  
  useEffect(() => {
    if (!shouldShowRunbookRecovery || replacementRunbookId || publishedRunbooks.length === 0) {
      return;
    }
    setReplacementRunbookId(String(publishedRunbooks[0].id));
  }, [publishedRunbooks, replacementRunbookId, shouldShowRunbookRecovery]);

  // QUEUED state - show processing indicator
  if (isQueued) {
    return (
      <TriageStatusCard
        title="AI Triage In Progress"
        description="The recommendation will appear automatically when ready."
        icon={<Loader2 className="motion-safe:animate-spin" />}
        appearance="processing"
      />
    );
  }

  // FAILED state - show error with retry option
  if (isFailed) {
    return (
      <TriageStatusCard
        title="AI Triage Failed"
        description={recommendation.error_message?.trim() || 'Unable to generate triage recommendation.'}
        icon={<TriangleAlert />}
        appearance="failed"
        action={onRetry ? { label: 'Retry AI Triage', onClick: onRetry, busy: isRetrying, icon: <RefreshCw /> } : undefined}
      />
    );
  }

  const reviewActions = isPending && canReview ? (
    <div className="ml-auto flex max-w-full shrink-0 flex-wrap items-center justify-end gap-2">
      <Button
        variant="neutral-secondary"
        size="medium"
        aria-label="Reject"
        aria-busy={isRejecting}
        onClick={() => setShowRejectDialog(true)}
        disabled={isRejecting || isAccepting}
        loading={isRejecting}
      >
        Reject
      </Button>
      <Button
        variant="brand-primary"
        size="medium"
        aria-label="Accept Recommendation"
        aria-busy={isAccepting}
        onClick={handleAccept}
        disabled={isAccepting || isRejecting}
        loading={isAccepting}
      >
        Accept Recommendation
      </Button>
    </div>
  ) : null;

  return (
    <section
      aria-label="AI Triage Recommendation"
      className={cn(styles.card, 'flex w-full min-w-0 flex-col border border-solid px-3 py-3 sm:px-4',
        isExpanded ? 'gap-3 bg-default-background' : 'gap-2 bg-neutral-50',
        isDarkTheme ? 'border-neutral-100' : 'border-neutral-400')}
    >
      <header className="flex w-full items-start gap-3">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1">
          <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
            <div className="flex items-center gap-2">
              <IconWrapper className="h-4 w-4 shrink-0 text-default-font" aria-hidden="true"><Sparkles /></IconWrapper>
              <h2 className="text-heading-3 font-heading-3 text-default-font">
                AI Triage Recommendation
              </h2>
            </div>
            <Badge variant={getDispositionVariant(recommendation.disposition)}>
              {formatDisposition(recommendation.disposition)}
            </Badge>
            {!isPending && (
              <Badge
                variant={getStatusVariant(recommendation.status)}
                icon={!isExpanded && recommendation.status === 'ACCEPTED' ? <Check className="h-3 w-3" /> :
                  !isExpanded && recommendation.status === 'REJECTED' ? <X className="h-3 w-3" /> : undefined}
              >
                {getStatusLabel(recommendation.status)}
              </Badge>
            )}
            {!isExpanded && isReviewed && (recommendation.reviewed_by || recommendation.reviewed_at) && (
              <span className="text-caption font-caption text-subtext-color">
                {(recommendation.status === 'ACCEPTED' || recommendation.status === 'REJECTED') && recommendation.reviewed_by && (
                  <>{getStatusLabel(recommendation.status)} by {recommendation.reviewed_by}{recommendation.reviewed_at ? ' · ' : ''}</>
                )}
                {recommendation.reviewed_at && <RelativeTime value={recommendation.reviewed_at} />}
              </span>
            )}
          </div>
          <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-x-3 gap-y-1">
            <span className="whitespace-nowrap text-caption font-caption text-subtext-color">
              <strong className={brandTextClass}>{formatConfidence(recommendation.confidence)}</strong> confidence
            </span>
            {contextIndicator}
          </div>
        </div>
        <IconButton
          className="shrink-0"
          variant="neutral-tertiary"
          icon={isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          aria-label={isExpanded ? "Collapse triage recommendation" : "Expand triage recommendation"}
          aria-expanded={isExpanded}
          aria-controls={contentId}
          onClick={() => setIsExpanded(!isExpanded)}
        />
      </header>

      {!isExpanded && reasons[0]?.trim() && (
        <InlineMarkdown
          content={reasons[0]}
          plainText
          className="block truncate text-caption font-caption text-subtext-color"
        />
      )}

      <div className="flex w-full min-w-0 flex-wrap items-center gap-2">
        <div className={cn(
          'flex min-w-0 flex-[1_1_15rem] items-center gap-2 border border-solid px-2.5 text-default-font',
          isExpanded ? 'py-1.5 text-heading-3 font-heading-3' : 'h-8 text-body-bold font-body-bold',
          recommendedAction.variant === 'escalate' && (isDarkTheme ? 'border-error-500 bg-error-1000' : 'border-error-500 bg-error-100'),
          recommendedAction.variant === 'dismiss' && (isDarkTheme ? 'border-success-500 bg-success-1000' : 'border-success-500 bg-success-100'),
          recommendedAction.variant === 'manual' && (isDarkTheme ? 'border-warning-500 bg-warning-1000' : 'border-warning-500 bg-warning-100'),
        )}>
          <IconWrapper
            aria-hidden="true"
            className={cn('h-4 w-4 shrink-0',
              recommendedAction.variant === 'escalate' && (isDarkTheme ? 'text-error-600' : 'text-error-800'),
              recommendedAction.variant === 'dismiss' && (isDarkTheme ? 'text-success-600' : 'text-success-800'),
              recommendedAction.variant === 'manual' && (isDarkTheme ? 'text-warning-600' : 'text-warning-800'))}
          >
            {recommendedAction.variant === 'escalate' ? <TriangleAlert /> :
              recommendedAction.variant === 'dismiss' ? <Check /> : <AlertCircle />}
          </IconWrapper>
          <span className={isExpanded ? undefined : "min-w-0 truncate"} title={isExpanded ? undefined : recommendedAction.text}>
            {recommendedAction.text}
          </span>
        </div>
        {!isExpanded && reviewActions}
      </div>

      <div id={contentId} hidden={!isExpanded} className={isExpanded ? "contents" : "hidden"}>
      {(reasons.length > 0 || hasSuggestedChanges || tasks.length > 0) && (
        <div className="flex min-w-0 flex-col border-b border-solid border-neutral-border">
          {reasons.length > 0 && (
            <TriageDetailRow
              label="Reasoning"
              preview={<InlineMarkdown content={reasons[0]} linkStyle="plain" className="block truncate text-body font-body text-subtext-color" />}
              hint={reasons.length > 1 ? `Show ${reasons.length - 1} more` : undefined}
            >
              <TriageDetailList>
                {reasons.map((reason, index) => (
                  <TriageDetailItem key={index}><ReasoningText text={reason} className="min-w-0" /></TriageDetailItem>
                ))}
              </TriageDetailList>
            </TriageDetailRow>
          )}
          {hasSuggestedChanges && (
            <TriageDetailRow
              label="Recommended Changes"
              preview={(
                <span className="flex min-w-0 flex-wrap items-center gap-1.5">
                  {suggestedState && <State state={suggestedState} variant="small" />}
                  {suggestedPriority && <Priority priority={suggestedPriority} size="mini" />}
                  {recommendation.suggested_assignee && <Badge variant="neutral" className="max-w-full">Assign to {recommendation.suggested_assignee}</Badge>}
                  {tagsToAdd.length > 0 && <Badge variant="neutral">+{tagsToAdd.length} {tagsToAdd.length === 1 ? 'tag' : 'tags'}</Badge>}
                  {tagsToRemove.length > 0 && <Badge variant="error">−{tagsToRemove.length} {tagsToRemove.length === 1 ? 'tag' : 'tags'}</Badge>}
                </span>
              )}
            >
              <dl className="grid min-w-0 grid-cols-[repeat(auto-fit,minmax(min(100%,10rem),1fr))] gap-x-4 gap-y-2">
                {suggestedState && (
                  <div className="flex min-w-0 flex-col items-start gap-1">
                    <dt className="text-caption-bold font-caption-bold text-subtext-color">Status</dt>
                    <dd><State state={suggestedState} variant="small" /></dd>
                  </div>
                )}
                {suggestedPriority && (
                  <div className="flex min-w-0 flex-col items-start gap-1">
                    <dt className="text-caption-bold font-caption-bold text-subtext-color">Priority</dt>
                    <dd><Priority priority={suggestedPriority} /></dd>
                  </div>
                )}
                {recommendation.suggested_assignee && (
                  <div className="flex min-w-0 flex-col items-start gap-1">
                    <dt className="text-caption-bold font-caption-bold text-subtext-color">Assignee</dt>
                    <dd className="text-body font-body text-default-font [overflow-wrap:anywhere]">{recommendation.suggested_assignee}</dd>
                  </div>
                )}
                {([
                  { label: 'Add Tags', tags: tagsToAdd, variant: 'neutral' },
                  { label: 'Remove Tags', tags: tagsToRemove, variant: 'error' },
                ] as const).map(({ label, tags, variant }) => tags.length > 0 && (
                  <div key={label} className="flex min-w-0 flex-col items-start gap-1">
                    <dt className="text-caption-bold font-caption-bold text-subtext-color">{label}</dt>
                    <dd className="flex min-w-0 flex-wrap items-center gap-1">
                      {tags.map((tag, index) => (
                        <Badge key={index} variant={variant} icon={<Tag className="h-3 w-3" />} className="max-w-full">{tag}</Badge>
                      ))}
                    </dd>
                  </div>
                ))}
              </dl>
            </TriageDetailRow>
          )}
          {tasks.length > 0 && (
            <TriageDetailRow
              label="Recommended Tasks"
              preview={<span className="block truncate text-body font-body text-subtext-color">{tasks[0]}</span>}
              hint={`${tasks.length} ${tasks.length === 1 ? 'task' : 'tasks'}`}
            >
              <TriageDetailList>
                {tasks.map((task, index) => <TriageDetailItem key={index}><span className="min-w-0">{task}</span></TriageDetailItem>)}
              </TriageDetailList>
            </TriageDetailRow>
          )}
        </div>
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
      </div>

      {shouldShowRunbookRecovery && (
        <>
          <div className="flex w-full flex-col gap-4 border border-warning-500 bg-warning-100 px-4 py-3">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-5 w-5 flex-none text-warning-700" />
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <span className="text-body-bold font-body-bold text-default-font">
                  Case Runbook unavailable
                </span>
                <span className="text-body font-body text-default-font">
                  {acceptError}
                </span>
              </div>
            </div>
            <div className="grid w-full gap-3 md:grid-cols-[minmax(0,1fr)_auto_auto] md:items-end">
              <Select
                className="w-full"
                label="Replacement Runbook"
                placeholder={isLoadingRunbooks ? 'Loading runbooks' : 'Choose a published runbook'}
                value={replacementRunbookId}
                onValueChange={setReplacementRunbookId}
              >
                {publishedRunbooks.map((runbook) => (
                  <Select.Item key={runbook.id} value={String(runbook.id)}>
                    {runbook.title || runbook.human_id}
                  </Select.Item>
                ))}
              </Select>
              <Button
                variant="brand-secondary"
                disabled={isAccepting || isRejecting || !replacementRunbookId}
                loading={isAccepting}
                onClick={() => onAccept(buildAcceptOptions({ case_runbook_id: Number(replacementRunbookId) }))}
              >
                Apply Replacement
              </Button>
              <Button
                variant="neutral-secondary"
                disabled={isAccepting || isRejecting}
                onClick={() => onAccept(buildAcceptOptions({ skip_case_runbook: true }))}
              >
                Continue Without Runbook
              </Button>
            </div>
          </div>
          <div className="flex h-px w-full flex-none bg-neutral-border" />
        </>
      )}
      {isExpanded && reviewActions}

      {/* Rejection Dialog */}
      <TriageRejectionDialog
        open={canReview && showRejectDialog}
        onOpenChange={setShowRejectDialog}
        onReject={onReject}
      />
    </section>
  );
}
