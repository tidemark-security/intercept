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
import { TriageConveyor } from './TriageConveyor';
import { getDispositionDismissalStatus } from './dismissalStatus';
import styles from './TriageRecommendationCard.module.css';

import { AlertCircle, ArrowRight, Bot, Check, ChevronDown, ChevronUp, RefreshCw, Sparkles, Tag, TriangleAlert, X, Zap } from 'lucide-react';
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

// Get inferred recommended action based on recommendation data
function getRecommendedAction(suggestedStatus: AlertStatus | null | undefined, requestsEscalation: boolean | undefined): {
  text: string;
  variant: 'escalate' | 'dismiss' | 'manual';
} {
  if (suggestedStatus && DISMISS_STATUSES.includes(suggestedStatus)) {
    return { text: 'Dismiss alert', variant: 'dismiss' };
  }
  if (requestsEscalation) {
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

function getTaskTitle(action: unknown): string {
  if (typeof action === 'string') return action;
  if (action && typeof action === 'object' && 'title' in action && typeof action.title === 'string') {
    return action.title;
  }
  return '';
}

interface TriageRecommendationCardProps {
  recommendation?: TriageRecommendationRead | null;
  onRequest?: () => void;
  onAccept: (options: AcceptRecommendationRequest) => void;
  onReject: (category: RejectionCategory, reason?: string) => void;
  onRetry?: () => void;
  onRerun?: (expectedCreatedAt: string) => void;
  contextChanged?: boolean | null;
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
  onRequest,
  onAccept,
  onReject,
  onRetry,
  onRerun,
  contextChanged,
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
  const isReviewed = recommendation != null && ['ACCEPTED', 'REJECTED', 'SUPERSEDED'].includes(recommendation.status);
  const result = isQueued || isFailed ? null : recommendation;
  const title = isQueued ? 'AI Triage In Progress' : isFailed ? 'AI Triage Failed' :
    result ? 'AI Triage Recommendation' : 'AI Triage Available';
  const [isExpanded, setIsExpanded] = useAlertPanelExpansion('triage-recommendation', defaultExpanded);
  const contentId = useId();
  const statusBodyClass = cn(
    'flex min-w-0 flex-1 flex-col items-center justify-center text-center',
    isExpanded ? 'gap-3 py-2' : 'gap-0.5 pb-1',
  );
  const [replacementRunbookId, setReplacementRunbookId] = useState<string>('');
  const [showRejectDialog, setShowRejectDialog] = useState(false);

  const dismissalStatus = result ? getDispositionDismissalStatus(result.disposition) : undefined;
  const suggestedStatus = dismissalStatus ?? result?.suggested_status;
  const requestsEscalation = !dismissalStatus && result?.request_escalate_to_case;

  const reasons = result?.reasoning_bullets ?? [];
  const tasks = dismissalStatus ? [] : (result?.recommended_actions ?? []).map(getTaskTitle).filter(Boolean);
  const tagsToAdd = result?.suggested_tags_add ?? [];
  const tagsToRemove = result?.suggested_tags_remove ?? [];
  const suggestedState = suggestedStatus ? alertStatusToUIState(suggestedStatus) : null;
  const suggestedPriority = result?.suggested_priority ? priorityToUIPriority(result.suggested_priority) : null;
  const hasSuggestedChanges = suggestedState || suggestedPriority || result?.suggested_assignee
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
  
  const recommendedAction = getRecommendedAction(suggestedStatus, requestsEscalation);
  const compactActionColor = {
    escalate: isDarkTheme ? 'text-error-400' : 'text-error-800',
    dismiss: isDarkTheme ? 'text-success-600' : 'text-success-900',
    manual: isDarkTheme ? 'text-warning-500' : 'text-warning-800',
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
  const statusAction = isFailed && onRetry
    ? { label: 'Retry AI Triage', onClick: onRetry, icon: <RefreshCw />, variant: 'neutral-secondary' as const }
    : !recommendation && onRequest
      ? { label: 'Request AI Triage', onClick: onRequest, icon: <Sparkles />, variant: 'brand-primary' as const }
      : null;

  const reviewActions = result && isPending && canReview ? (
    <div className="flex w-full max-w-full flex-wrap items-center gap-2">
      {onRerun && (
        <Button
          size="medium"
          variant="neutral-secondary"
          icon={<RefreshCw aria-hidden="true" />}
          aria-label="Rerun AI Triage"
          aria-busy={isRetrying}
          disabled={isRetrying || isAccepting || isRejecting}
          loading={isRetrying}
          onClick={() => onRerun(result.created_at)}
        >
          Rerun AI Triage
        </Button>
      )}
      <div className="ml-auto flex max-w-full flex-wrap items-center justify-end gap-2">
        <Button
          variant="neutral-secondary"
          size="medium"
          icon={<X aria-hidden="true" />}
          className={isDarkTheme
            ? 'enabled:border-warning-500 enabled:hover:bg-warning-500/10 enabled:active:bg-warning-500/20 [&:enabled>span]:text-warning-500'
            : 'enabled:border-warning-800 enabled:hover:bg-warning-800/10 enabled:active:bg-warning-800/20 [&:enabled>span]:text-warning-800'}
          aria-label="Reject"
          aria-busy={isRejecting}
          onClick={() => setShowRejectDialog(true)}
          disabled={isRejecting || isAccepting || isRetrying}
          loading={isRejecting}
        >
          Reject
        </Button>
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

  return (
    <div className={styles.frame}>
      <section
        aria-label={title}
        data-layout={isExpanded ? 'expanded' : 'compact'}
        className={cn(
          styles.card,
          'flex w-full min-w-0 flex-col gap-2 border px-3 py-3 sm:px-4',
          isExpanded ? 'bg-default-background' : 'bg-neutral-50',
          isQueued ? 'border-solid border-brand-800' :
            isFailed ? (isDarkTheme ? 'border-solid border-error-500' : 'border-solid border-error-200') :
            result ? (isDarkTheme ? 'border-solid border-neutral-100' : 'border-solid border-neutral-400') :
            'border-dashed border-neutral-border',
        )}
      >
        <header className="flex w-full shrink-0 items-center gap-3">
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
                  <Badge variant={getDispositionVariant(result.disposition)} className="h-5">
                    {formatDisposition(result.disposition)}
                  </Badge>
                  {!isPending && (
                    <Badge
                      variant={getStatusVariant(result.status)}
                      className="h-5"
                      icon={!isExpanded && result.status === 'ACCEPTED' ? <Check className="h-3 w-3" /> :
                        !isExpanded && result.status === 'REJECTED' ? <X className="h-3 w-3" /> : undefined}
                    >
                      {getStatusLabel(result.status)}
                    </Badge>
                  )}
                  {!isExpanded && isReviewed && (result.reviewed_by || result.reviewed_at) && (
                  <span className="min-w-0 max-w-full truncate text-caption font-caption text-subtext-color">
                      {(result.status === 'ACCEPTED' || result.status === 'REJECTED') && result.reviewed_by && (
                        <>{getStatusLabel(result.status)} by {result.reviewed_by}{result.reviewed_at ? ' · ' : ''}</>
                      )}
                      {result.reviewed_at && <RelativeTime value={result.reviewed_at} />}
                    </span>
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

        <div
          id={contentId}
          className="flex min-w-0 grow flex-col gap-2"
          role="group"
          aria-label={isExpanded ? 'Triage details' : 'Triage summary'}
        >
          {result ? (
            <>
              {contextChanged && (
                <p className="text-caption font-caption text-subtext-color">Context changed since triage</p>
              )}

              {!isExpanded && reasons[0]?.trim() && (
                <InlineMarkdown
                  content={reasons[0]}
                  plainText
                  className="block truncate text-caption font-caption text-subtext-color"
                />
              )}

              <div className={cn("flex w-full min-w-0 flex-wrap items-center gap-2", isExpanded && "pb-0.5")}>
                <div className={cn(
                  'flex min-w-0 flex-[1_1_15rem] items-center gap-2',
                  isExpanded ? cn(
                    'border border-solid px-2.5 py-1.5 text-heading-3 font-heading-3 text-default-font',
                    recommendedAction.variant === 'escalate' && (isDarkTheme ? 'border-error-500 bg-error-1000' : 'border-error-500 bg-error-100'),
                    recommendedAction.variant === 'dismiss' && (isDarkTheme ? 'border-success-500 bg-success-1000' : 'border-success-500 bg-success-100'),
                    recommendedAction.variant === 'manual' && (isDarkTheme ? 'border-warning-500 bg-warning-1000' : 'border-warning-500 bg-warning-100'),
                  ) : cn('h-8 text-body-bold font-body-bold', compactActionColor),
                )}>
                  <IconWrapper
                    aria-hidden="true"
                    className={cn('h-4 w-4 shrink-0', isExpanded && cn(
                      recommendedAction.variant === 'escalate' && (isDarkTheme ? 'text-error-600' : 'text-error-800'),
                      recommendedAction.variant === 'dismiss' && (isDarkTheme ? 'text-success-600' : 'text-success-800'),
                      recommendedAction.variant === 'manual' && (isDarkTheme ? 'text-warning-600' : 'text-warning-800'),
                    ))}
                  >
                    {recommendedAction.variant === 'escalate' ? <TriangleAlert /> :
                      recommendedAction.variant === 'dismiss' ? <Check /> : <AlertCircle />}
                  </IconWrapper>
                  <span className={isExpanded ? undefined : "min-w-0 truncate"} title={isExpanded ? undefined : recommendedAction.text}>
                    {recommendedAction.text}
                  </span>
                </div>
              </div>

              {isExpanded && (
                <>
                  {(reasons.length > 0 || hasSuggestedChanges || tasks.length > 0 || hasContextDetail) && (
                    <div className="flex min-w-0 flex-col border-b border-solid border-neutral-border">
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
                              {suggestedPriority && <Priority priority={suggestedPriority} size="mini" />}
                              {result.suggested_assignee && <Badge variant="neutral" className="max-w-full">Assign to {result.suggested_assignee}</Badge>}
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
                            {result.suggested_assignee && (
                              <div className="flex min-w-0 flex-col items-start gap-1">
                                <dt className="text-caption-bold font-caption-bold text-subtext-color">Assignee</dt>
                                <dd className="text-body font-body text-default-font [overflow-wrap:anywhere]">{result.suggested_assignee}</dd>
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

                  {result.status === 'REJECTED' && result.rejection_reason && (
                    <TriageDetailRow
                      label="Rejection Reason"
                      preview={<span className="block truncate text-caption font-caption text-subtext-color">{result.rejection_reason}</span>}
                    >
                      <p className="whitespace-pre-line text-body font-body text-default-font [overflow-wrap:anywhere]">{result.rejection_reason}</p>
                    </TriageDetailRow>
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
          ) : isQueued ? (
            <div
              role="status"
              className={cn("flex flex-1 flex-col items-center justify-center text-center", isExpanded ? "gap-3 py-2" : "gap-2 py-1")}
            >
              <TriageConveyor expanded={isExpanded} className={brandTextClass} />
              <p className="text-body font-body text-subtext-color">
                The recommendation will appear automatically when ready.
              </p>
            </div>
          ) : isFailed ? (
            <div className={statusBodyClass}>
              <TriageRobot state="failed" className={failureAccentClass} />
              <div className={cn(
                'flex w-full min-w-0 items-center justify-center',
                isExpanded ? 'flex-col gap-1' : 'flex-wrap gap-x-2 gap-y-0.5',
              )}>
                <p
                  className={cn(
                    'max-w-full whitespace-pre-line text-body-bold font-body-bold text-default-font [overflow-wrap:anywhere]',
                    !isExpanded && 'line-clamp-2',
                  )}
                >
                  {failureDetail}
                </p>
                <p className="text-body font-body text-subtext-color">
                  {onRetry ? 'If retrying fails, ask' : 'Ask'} an admin to {diagnosticAction}.
                </p>
              </div>
            </div>
          ) : (
            <div className={statusBodyClass}>
              <TriageRobot state="available" className={brandTextClass} />
              <p className="text-body font-body text-subtext-color">Get a suggested disposition and next steps.</p>
            </div>
          )}
        </div>

        {(reviewActions || statusAction) && (
          <div className="flex w-full min-w-0 shrink-0 items-center">
            {reviewActions}
            {statusAction && (
              <Button
                className={isFailed ? undefined : 'ml-auto'}
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
