import { useEffect, useId, useMemo, useState, type ReactNode } from 'react';
import { Accordion } from '@tidemark-security/ux';

import { Badge } from '@/components/data-display/Badge';
import { RelativeTime } from '@/components/data-display/RelativeTime';
import { InlineMarkdown } from '@/components/data-display/InlineMarkdown';
import { Button } from '@/components/buttons/Button';
import { IconButton } from '@/components/buttons/IconButton';
import { Select } from '@/components/forms/Select';
import { Tooltip } from '@/components/overlays/Tooltip';
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
import { TriageRejectButton, TriageRejectionDialog } from './TriageRejectionDialog';
import { TriageConveyor } from './TriageConveyor';
import { getDispositionDismissalStatus } from './dismissalStatus';
import styles from './TriageRecommendationCard.module.css';

import { AlertCircle, ArrowRight, Bot, Check, ChevronDown, ChevronUp, RefreshCw, Sparkles, Tag, TriangleAlert, X, Zap } from 'lucide-react';
function formatTriageLabel(value: string): string {
  return value
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// Helper to format confidence as percentage
function formatConfidence(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
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

// Get inferred recommended action based on recommendation data
function getRecommendedAction(suggestedStatus: AlertStatus | null | undefined, requestsEscalation: boolean | undefined): {
  text: string;
  variant: 'escalate' | 'dismiss' | 'manual';
} {
  if (suggestedStatus && DISMISS_STATUSES.includes(suggestedStatus)) {
    return { text: 'Dismiss alert', variant: 'dismiss' };
  }
  if (requestsEscalation) {
    return { text: 'Investigate alert', variant: 'escalate' };
  }
  return { text: 'Low confidence - Investigate alert', variant: 'manual' };
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
        <span className={cn(styles.disclosure, 'grid w-full min-w-0 items-center gap-x-3 gap-y-1 px-1 py-3')}>
          <span className="self-start text-heading-3 font-heading-3 text-default-font">{label}</span>
          {!open && preview && <span className={cn(styles.preview, 'min-w-0')}>{preview}</span>}
          <span className={cn(styles.toggle, 'flex shrink-0 items-center justify-end gap-2 self-start pt-0.5 text-caption font-caption text-subtext-color')}>
            {hint && <span className={open ? 'invisible' : undefined}>{hint}</span>}
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

function TriageRobot({ state, className }: { state: 'available' | 'failed'; className: string }) {
  return (
    <span aria-hidden="true" data-robot-state={state} className={cn(styles.robot, className)}>
      {state === 'available' && <span className={styles.speedLines} />}
      <IconWrapper className={styles.robotIcon}>
        <Bot />
      </IconWrapper>
      {state === 'failed' && (
        <span className={cn(styles.sleep, 'text-caption-bold font-caption-bold')}>
          <span>Z</span>
          <span>z</span>
          <span>z</span>
        </span>
      )}
    </span>
  );
}

function getRecommendedTask(action: unknown) {
  if (typeof action === 'string' && action) return { title: action };
  if (action && typeof action === 'object' && 'title' in action && typeof action.title === 'string') {
    if (!action.title) return null;
    const description = 'description' in action && typeof action.description === 'string'
      ? action.description.trim()
      : undefined;
    return { title: action.title, description };
  }
  return null;
}

function TriagePreviewBadge({ label, heading, variant = 'neutral', children }: {
  label: string;
  heading: string;
  variant?: 'neutral' | 'error';
  children: ReactNode;
}) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>
        <Badge
          variant={variant}
          tabIndex={0}
          className="cursor-help focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus-border"
        >
          {label}
        </Badge>
      </Tooltip.Trigger>
      <Tooltip.Content
        side="top"
        align="start"
        sideOffset={6}
        collisionPadding={8}
        className="w-max max-w-[min(26rem,var(--radix-tooltip-content-available-width))] max-h-[min(18rem,var(--radix-tooltip-content-available-height))] overflow-y-auto border-neutral-border bg-default-background px-3 py-2 text-default-font"
      >
        <span className="text-caption-bold font-caption-bold">{heading}</span>
        {children}
      </Tooltip.Content>
    </Tooltip.Root>
  );
}

function TriageTagBadges({ tags, variant }: { tags: string[]; variant: 'neutral' | 'error' }) {
  return (
    <div className="flex min-w-0 max-w-full flex-wrap items-center gap-1">
      {tags.map((tag, index) => (
        <Badge
          key={index}
          variant={variant}
          icon={<Tag aria-hidden="true" className="h-3 w-3" />}
          className="h-auto min-h-6 max-w-full [&>span:last-child]:line-clamp-none [&>span:last-child]:[overflow-wrap:anywhere]"
        >
          {tag}
        </Badge>
      ))}
    </div>
  );
}

interface TriageRecommendationCardProps {
  recommendation?: TriageRecommendationRead | null;
  className?: string;
  onRequest?: () => void;
  onAccept: (options: AcceptRecommendationRequest) => void;
  onReject: (category: RejectionCategory, reason?: string) => void;
  onRetry?: () => void;
  onRerun?: (expectedCreatedAt: string) => void;
  hasCurrentContext?: boolean;
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
  className,
  onRequest,
  onAccept,
  onReject,
  onRetry,
  onRerun,
  hasCurrentContext = false,
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
  const failureAccentClass = isDarkTheme ? 'text-error-400' : 'text-error-800';

  const isPending = recommendation?.status === 'PENDING';
  const isQueued = recommendation?.status === 'QUEUED';
  const isFailed = recommendation?.status === 'FAILED';
  const result = isQueued || isFailed ? null : recommendation;
  const isRejected = result?.status === 'REJECTED';
  const isReviewed = isRejected || result?.status === 'ACCEPTED';
  const title = isQueued ? 'AI Triage In Progress' : isFailed ? 'AI Triage Failed' :
    result ? 'AI Triage Recommendation' : 'AI Triage Available';
  const [expandResults, setExpandResults] = useAlertPanelExpansion('triage-recommendation', defaultExpanded);
  const isExpanded = Boolean(result) && expandResults;
  const reserveReviewBadgeSpace = !isExpanded && (isPending || isReviewed);
  const contentId = useId();
  const [replacementRunbookId, setReplacementRunbookId] = useState<string>('');
  const [showRejectDialog, setShowRejectDialog] = useState(false);

  const dismissalStatus = result ? getDispositionDismissalStatus(result.disposition) : undefined;
  const suggestedStatus = dismissalStatus ?? result?.suggested_status;
  const requestsEscalation = !dismissalStatus && result?.request_escalate_to_case;

  const reasons = result?.reasoning_bullets ?? [];
  const tasks = dismissalStatus ? [] : (result?.recommended_actions ?? []).map(getRecommendedTask).filter(task => task !== null);
  const tagChanges = ([
    { label: 'Add Tags', tags: result?.suggested_tags_add ?? [], sign: '+', variant: 'neutral' },
    { label: 'Remove Tags', tags: result?.suggested_tags_remove ?? [], sign: '−', variant: 'error' },
  ] as const)
    .filter(({ tags }) => tags.length > 0)
    .map(change => ({ ...change, countLabel: `${change.sign}${change.tags.length} ${change.tags.length === 1 ? 'tag' : 'tags'}` }));
  const suggestedState = suggestedStatus ? alertStatusToUIState(suggestedStatus) : null;
  const suggestedPriority = result?.suggested_priority ? priorityToUIPriority(result.suggested_priority) : null;
  const hasSuggestedChanges = suggestedState || suggestedPriority || result?.suggested_assignee
    || tagChanges.length > 0;
  const showCompactSummary = !isExpanded && Boolean(suggestedPriority || reasons.length || tagChanges.length || tasks.length);
  const priorityBadge = suggestedPriority && <Priority priority={suggestedPriority} size="mini" />;
  const taskDetails = (
    <TriageDetailList>
      {tasks.map(({ title, description }, index) => (
        <TriageDetailItem key={index}>
          <div className="min-w-0">
            <div>{title}</div>
            {description && <InlineMarkdown content={description} linkStyle="plain" className="block whitespace-pre-line text-subtext-color" />}
          </div>
        </TriageDetailItem>
      ))}
    </TriageDetailList>
  );

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
  
  const recommendedAction = getRecommendedAction(suggestedStatus, requestsEscalation);
  const actionBannerClass = cn(
    'border border-solid px-2.5',
    isReviewed ? 'border-neutral-border bg-neutral-100' : {
      escalate: isDarkTheme ? 'border-error-500 bg-error-1000' : 'border-error-500 bg-error-100',
      dismiss: isDarkTheme ? 'border-success-500 bg-success-1000' : 'border-success-500 bg-success-100',
      manual: isDarkTheme ? 'border-warning-500 bg-warning-1000' : 'border-warning-500 bg-warning-100',
    }[recommendedAction.variant],
  );
  const actionIconColor = !isReviewed && {
    escalate: isDarkTheme ? 'text-error-600' : 'text-error-800',
    dismiss: isDarkTheme ? 'text-success-600' : 'text-success-800',
    manual: isDarkTheme ? 'text-warning-600' : 'text-warning-800',
  }[recommendedAction.variant];
  const savedContext = result?.applied_context_entries ?? [];
  const firstContextBody = savedContext[0]?.body;
  const hasContextPreview = typeof firstContextBody === 'string' && firstContextBody.trim() !== '';
  const isContextVerified = result?.context_snapshot_verified;
  const hasContextDetail = isContextVerified || savedContext.length > 0 || hasCurrentContext;
  const contextIndicator = isContextVerified && savedContext.length > 0 ? (
    <span className="inline-flex items-center gap-1.5 text-caption font-caption text-subtext-color" title="Analyst context supplied to this triage run">
      <Check aria-hidden="true" className={cn("h-4 w-4 shrink-0", brandTextClass)} />
      {savedContext.length} context {savedContext.length === 1 ? 'entry' : 'entries'} supplied
    </span>
  ) : null;
  const shouldShowRunbookRecovery = Boolean(
    isPending &&
    canReview &&
    requestsEscalation &&
    acceptError &&
    acceptError.toLowerCase().includes('runbook')
  );
  const { data: publishedRunbooksData, isLoading: isLoadingRunbooks } = useCaseRunbooks(['PUBLISHED'], null, shouldShowRunbookRecovery);
  const publishedRunbooks = useMemo(() => publishedRunbooksData?.items ?? [], [publishedRunbooksData?.items]);
  
  useEffect(() => {
    if (!shouldShowRunbookRecovery || replacementRunbookId || publishedRunbooks.length === 0) {
      return;
    }
    setReplacementRunbookId(String(publishedRunbooks[0].id));
  }, [publishedRunbooks, replacementRunbookId, shouldShowRunbookRecovery]);

  const failureDetail = recommendation?.error_message?.trim() || 'Unable to generate triage recommendation.';
  const diagnosticAction = failureDetail === 'Task queue unavailable'
    ? 'check the task queue for this alert'
    : 'look up the alert ID in the triage worker logs';
  const statusMessage = isFailed ? {
    summary: failureDetail,
    detail: `${onRetry ? 'If retrying fails, ask' : 'Ask'} an admin to ${diagnosticAction}.`,
  } : isQueued ? {
    summary: 'Triage request submitted.',
    detail: 'Results appear here automatically.',
  } : {
    summary: 'Generate a recommendation.',
    detail: 'Get a suggested disposition and next steps.',
  };
  const statusAction = isFailed && onRetry
    ? { label: 'Retry', onClick: onRetry, icon: <RefreshCw />, variant: 'neutral-secondary' as const }
    : !recommendation && onRequest
      ? { label: 'Start', onClick: onRequest, icon: <Sparkles />, variant: 'brand-primary' as const }
      : null;

  // Reserve the same space for review buttons when they wrap in narrow panes.
  const reserveReviewSpace = !isExpanded && isReviewed;
  const reviewActions = result && canReview && (isPending || reserveReviewSpace) ? (
    <div
      className={cn('col-start-1 row-start-1 flex w-full min-w-0 flex-wrap items-center gap-2', reserveReviewSpace && 'invisible')}
      inert={reserveReviewSpace || undefined}
      aria-hidden={reserveReviewSpace || undefined}
    >
      {onRerun && (
        <Button
          size="medium"
          variant="neutral-secondary"
          icon={<RefreshCw aria-hidden="true" />}
          aria-label="Rerun"
          aria-busy={isRetrying}
          disabled={isRetrying || isAccepting || isRejecting}
          loading={isRetrying}
          onClick={() => onRerun(result.created_at)}
        >
          Rerun
        </Button>
      )}
      <div className="ml-auto flex max-w-full flex-wrap items-center justify-end gap-2">
        <TriageRejectButton
          aria-busy={isRejecting}
          onClick={() => setShowRejectDialog(true)}
          disabled={isRejecting || isAccepting || isRetrying}
          loading={isRejecting}
        />
        <Button
          variant="brand-primary"
          size="medium"
          icon={<Check aria-hidden="true" />}
          aria-label="Accept Recommendation"
          aria-busy={isAccepting}
          onClick={handleAccept}
          disabled={isAccepting || isRejecting || isRetrying}
          loading={isAccepting}
        >
          Accept Recommendation
        </Button>
      </div>
    </div>
  ) : null;

  const rejectionCategory = isRejected && result.rejection_category
    ? formatTriageLabel(result.rejection_category)
    : null;
  const rejectionReason = isRejected ? result.rejection_reason?.trim() : null;
  const reviewDetails = isReviewed && (result.reviewed_by || result.reviewed_at || rejectionCategory || rejectionReason) ? (
    <div
      role="group"
      aria-label={isRejected ? 'Rejection details' : 'Acceptance details'}
      className={cn(
        "col-start-1 row-start-1 flex min-h-8 w-full min-w-0 flex-col justify-center text-caption font-caption text-subtext-color [overflow-wrap:anywhere]",
        // Two compact caption lines occupy the same height as the review buttons.
        isExpanded && "gap-0.5",
      )}
    >
      {(result.reviewed_by || result.reviewed_at) && (
        <p>
          {result.reviewed_by && (
            <>{getStatusLabel(result.status)} by <span className="text-default-font">{result.reviewed_by}</span>{result.reviewed_at && ' · '}</>
          )}
          {result.reviewed_at && <RelativeTime value={result.reviewed_at} />}
        </p>
      )}
      {(rejectionCategory || rejectionReason) && (
        <p className="whitespace-pre-line">
          <span className="mr-2 text-caption-bold font-caption-bold text-default-font">Rejection reason</span>
          {rejectionCategory}{rejectionCategory && rejectionReason && ' · '}{rejectionReason}
        </p>
      )}
    </div>
  ) : null;
  const hasReviewFooter = Boolean(reviewActions || reviewDetails || (!isExpanded && (isPending || isReviewed)));

  return (
    <div className={styles.frame}>
      <section
        aria-label={title}
        data-layout={isExpanded ? 'expanded' : 'compact'}
        className={cn(
          result && styles.card,
          'mt-2 flex w-full min-w-0 flex-col gap-2 border-t border-solid border-neutral-border pt-4',
          className,
        )}
      >
        <header className={cn('flex w-full shrink-0 items-center gap-3', !result && 'min-h-8')}>
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1">
            <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
              <div className="flex min-w-0 items-center gap-2">
                <IconWrapper
                  className={cn('h-4 w-4 shrink-0', isQueued ? brandTextClass :
                    isFailed ? failureAccentClass : 'text-default-font')}
                  aria-hidden="true"
                >
                  {isQueued ? <Zap /> : isFailed ? <TriangleAlert /> : <Sparkles />}
                </IconWrapper>
                <h2 className="text-heading-3 font-heading-3 text-default-font">{title}</h2>
              </div>
              {result && (
                <>
                  {(!isPending || reserveReviewBadgeSpace) && (
                    <div
                      className={cn('flex', reserveReviewBadgeSpace && 'h-5 min-w-[5.5rem] shrink-0')}
                      aria-hidden={isPending || undefined}
                    >
                      {!isPending && (
                        <Badge
                          variant={getStatusVariant(result.status)}
                          className="h-5"
                          icon={result.status === 'ACCEPTED' ? <Check aria-hidden="true" className="h-3 w-3" /> :
                            isRejected ? <X aria-hidden="true" className="h-3 w-3" /> : undefined}
                        >
                          {getStatusLabel(result.status)}
                        </Badge>
                      )}
                    </div>
                  )}
                  {!isExpanded && result.status === 'SUPERSEDED' && result.reviewed_at && (
                    <span className="min-w-0 max-w-full truncate text-caption font-caption text-subtext-color"><RelativeTime value={result.reviewed_at} /></span>
                  )}
                </>
              )}
            </div>
            {result && (
              <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-x-3 gap-y-1">
                <span className="whitespace-nowrap text-caption font-caption text-subtext-color">
                  <strong className={brandTextClass}>{formatConfidence(result.confidence)}</strong> confidence
                </span>
                {contextIndicator}
              </div>
            )}
          </div>
          {result && (
            <IconButton
              className="shrink-0"
              variant="neutral-tertiary"
              icon={isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              aria-label={isExpanded ? "Collapse triage recommendation" : "Expand triage recommendation"}
              aria-expanded={isExpanded}
              aria-controls={contentId}
              onClick={() => setExpandResults(!isExpanded)}
            />
          )}
          {statusAction && (
            <Button
              className="shrink-0"
              size="medium"
              variant={statusAction.variant}
              onClick={statusAction.onClick}
              aria-label={statusAction.label}
              aria-busy={isRetrying}
              disabled={isRetrying}
              loading={isRetrying}
              icon={statusAction.icon}
            >
              {statusAction.label}
            </Button>
          )}
        </header>

        <div
          id={contentId}
          className={cn(
            "flex min-w-0 grow flex-col gap-2",
            !isExpanded && hasReviewFooter && !shouldShowRunbookRecovery && "justify-center",
          )}
          role="group"
          aria-label={isExpanded ? 'Triage details' : 'Triage summary'}
        >
          {result ? (
            <>
              {/* Offset the compact banner's padding and leave room below it. */}
              <div className={cn(
                "flex w-full min-w-0 flex-wrap items-center gap-x-3 gap-y-1",
                isExpanded ? "pb-0.5" : cn(actionBannerClass, "-mt-1 -mb-0.5 py-2.5"),
              )}>
                <div className={cn(
                  'flex min-w-0 max-w-full items-center gap-2',
                  isReviewed ? 'text-subtext-color' : 'text-default-font',
                  isExpanded ? cn(
                    'w-full py-1.5 text-heading-3 font-heading-3',
                    actionBannerClass,
                  ) : 'min-h-8 text-heading-2 font-heading-2',
                )}>
                  <IconWrapper
                    aria-hidden="true"
                    className={cn('shrink-0', isExpanded ? 'h-4 w-4' : 'h-5 w-5', actionIconColor)}
                  >
                    {recommendedAction.variant === 'escalate' ? <TriangleAlert /> :
                      recommendedAction.variant === 'dismiss' ? <Check /> : <AlertCircle />}
                  </IconWrapper>
                  <span>{recommendedAction.text}</span>
                </div>
                {showCompactSummary && (
                  <Tooltip.Provider delayDuration={150}>
                    <div
                      role="group"
                      aria-label="Recommendation preview"
                      className="flex min-w-0 max-w-full flex-wrap items-center gap-1.5 border-l border-solid border-neutral-border pl-3"
                    >
                      {priorityBadge}
                      {reasons.length > 0 && (
                        <TriagePreviewBadge label={`${reasons.length} ${reasons.length === 1 ? 'reason' : 'reasons'}`} heading="Reasoning">
                          <TriageDetailList>
                            {reasons.map((reason, index) => (
                              <TriageDetailItem key={index}><InlineMarkdown content={reason} linkStyle="plain" /></TriageDetailItem>
                            ))}
                          </TriageDetailList>
                        </TriagePreviewBadge>
                      )}
                      {tagChanges.map(({ label, tags, countLabel, variant }) => (
                        <TriagePreviewBadge key={label} label={countLabel} heading={label} variant={variant}>
                          <TriageTagBadges tags={tags} variant={variant} />
                        </TriagePreviewBadge>
                      ))}
                      {tasks.length > 0 && (
                        <TriagePreviewBadge
                          label={`${tasks.length} recommended ${tasks.length === 1 ? 'task' : 'tasks'}`}
                          heading="Recommended Tasks"
                        >
                          {taskDetails}
                        </TriagePreviewBadge>
                      )}
                    </div>
                  </Tooltip.Provider>
                )}
              </div>

              {isExpanded && (
                <>
                  {(reasons.length > 0 || hasSuggestedChanges || tasks.length > 0 || hasContextDetail) && (
                    <div className="my-1 flex min-w-0 flex-col border-b border-solid border-neutral-border">
                      {hasContextDetail && (
                        <TriageDetailRow
                          label={isContextVerified ? 'Context at Triage' : 'Saved Context'}
                          preview={(hasContextPreview || !isContextVerified || savedContext.length === 0) && (
                            <span className="block truncate text-body font-body text-subtext-color">
                              {!isContextVerified && <span>Context for this run is unverified</span>}
                              {hasContextPreview && (
                                <>
                                  {!isContextVerified && ' · '}
                                  <InlineMarkdown content={firstContextBody} linkStyle="plain" />
                                </>
                              )}
                              {savedContext.length === 0 && (isContextVerified ? 'No entries supplied' : ' · No entries saved')}
                            </span>
                          )}
                          hint={savedContext.length > 0 ? 'View saved entries' : undefined}
                        >
                          <TriageDetailList>
                            {!isContextVerified && (
                              <TriageDetailItem><span>Context for this run is unverified</span></TriageDetailItem>
                            )}
                            {savedContext.map((entry, index) => (
                              <TriageDetailItem key={entry.id ?? index}>
                                <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
                                  {typeof entry.body === 'string' && <ReasoningText text={entry.body} className="min-w-0" />}
                                  {(typeof entry.author === 'string' || typeof entry.updated_at === 'string') && (
                                    <span className="text-caption font-caption text-subtext-color">
                                      {typeof entry.author === 'string' && entry.author}
                                      {typeof entry.updated_at === 'string' && (
                                        <>{entry.author && ' · '}<RelativeTime value={entry.updated_at} /></>
                                      )}
                                    </span>
                                  )}
                                </div>
                              </TriageDetailItem>
                            ))}
                            {savedContext.length === 0 && (
                              <TriageDetailItem>
                                <span>{isContextVerified ? 'No analyst context was supplied for this run.' : 'No analyst context was saved for this run.'}</span>
                              </TriageDetailItem>
                            )}
                          </TriageDetailList>
                        </TriageDetailRow>
                      )}
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
                            <span className="flex min-w-0 items-center gap-1.5 overflow-hidden">
                              {suggestedState && <State state={suggestedState} variant="small" />}
                              {priorityBadge}
                              {result.suggested_assignee && <Badge variant="neutral" className="max-w-full">Assign to {result.suggested_assignee}</Badge>}
                              {tagChanges.map(({ label, countLabel, variant }) => (
                                <Badge key={label} variant={variant}>{countLabel}</Badge>
                              ))}
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
                            {result.suggested_assignee && (
                              <div className="flex min-w-0 flex-col items-start gap-1">
                                <dt className="text-caption-bold font-caption-bold text-subtext-color">Assignee</dt>
                                <dd className="text-body font-body text-default-font [overflow-wrap:anywhere]">{result.suggested_assignee}</dd>
                              </div>
                            )}
                            {tagChanges.map(({ label, tags, variant }) => (
                              <div key={label} className="flex min-w-0 flex-col items-start gap-1">
                                <dt className="text-caption-bold font-caption-bold text-subtext-color">{label}</dt>
                                <dd className="min-w-0 max-w-full">
                                  <TriageTagBadges tags={tags} variant={variant} />
                                </dd>
                              </div>
                            ))}
                          </dl>
                        </TriageDetailRow>
                      )}
                      {tasks.length > 0 && (
                        <TriageDetailRow
                          label="Recommended Tasks"
                          preview={<span className="block truncate text-body font-body text-subtext-color">{tasks[0].title}</span>}
                          hint={`${tasks.length} ${tasks.length === 1 ? 'task' : 'tasks'}`}
                        >
                          {taskDetails}
                        </TriageDetailRow>
                      )}
                    </div>
                  )}

                  {/* Superseded Notice */}
                  {result.status === 'SUPERSEDED' && (
                    <>
                      <div className="flex w-full items-center gap-2 rounded-md bg-neutral-100 p-3">
                        <span className="text-caption font-caption text-subtext-color">
                          This recommendation has been superseded by a newer one.
                        </span>
                      </div>
                      <div className="flex h-px w-full flex-none bg-neutral-border" />
                    </>
                  )}
                </>
              )}

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
            </>
          ) : (
            <div
              role={isQueued ? 'status' : undefined}
              className="flex min-h-[4.5rem] min-w-0 flex-1 items-center gap-3 border border-solid border-neutral-border bg-neutral-100 px-3 py-1"
            >
              <div className="flex min-h-12 w-[min(13rem,32%)] shrink-0 items-center justify-center">
                {isQueued ? <TriageConveyor className={brandTextClass} /> : (
                  <TriageRobot state={isFailed ? 'failed' : 'available'} className={cn('max-w-full', isFailed ? failureAccentClass : brandTextClass)} />
                )}
              </div>
              <div className="flex min-w-0 flex-1 flex-col justify-center gap-0.5 self-stretch text-body font-body text-default-font [overflow-wrap:anywhere]">
                <p className="whitespace-pre-line">{statusMessage.summary}</p>
                <p className="text-subtext-color">{statusMessage.detail}</p>
              </div>
            </div>
          )}
        </div>

        {hasReviewFooter && (
          <div className="grid min-h-8 w-full min-w-0 shrink-0 grid-cols-1 pt-0.5">
            {reviewActions}
            {reviewDetails}
          </div>
        )}

        {/* Rejection Dialog */}
        <TriageRejectionDialog
          open={isPending && canReview && showRejectDialog}
          onOpenChange={setShowRejectDialog}
          onReject={onReject}
        />
      </section>
    </div>
  );
}
