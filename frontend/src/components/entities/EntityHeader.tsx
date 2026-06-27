"use client";

import React, { RefObject } from "react";
import { useBreakpointContext } from "@/contexts/BreakpointContext";
import { useTheme } from "@/contexts/ThemeContext";
import { cn } from "@/utils/cn";
import { Button } from "@/components/buttons/Button";
import { IconButton } from "@/components/buttons/IconButton";
import { LinkButton } from "@/components/timeline/LinkButton";
import { DropdownMenu, DropdownMenuRoot, DropdownMenuTrigger, DropdownMenuContent } from "@/components/overlays/DropdownMenu";
import { AssigneeSelector } from "@/components/forms/AssigneeSelector";
import { TimelineFilter } from "@/components/timeline/TimelineFilter";
import { AdaptiveToggleLabel } from "@/components/timeline/AdaptiveToggleLabel";
import { CaseClosureModal } from "@/components/entities/CaseClosureModal";
import { TriageRejectionDialog } from "@/components/triage/TriageRejectionDialog";
import { ToggleGroup } from "@/components/buttons/ToggleGroup";

import type { AlertStatus } from "@/types/generated/models/AlertStatus";
import type { AcceptRecommendationRequest } from "@/types/generated/models/AcceptRecommendationRequest";
import type { CaseStatus } from "@/types/generated/models/CaseStatus";
import type { RejectionCategory } from "@/types/generated/models/RejectionCategory";
import type { TaskStatus } from "@/types/generated/models/TaskStatus";
import type { TriageRecommendationRead } from "@/types/generated/models/TriageRecommendationRead";
import type { Priority as PriorityType } from "@/types/generated/models/Priority";
import type { TimelineItem } from "@/types/timeline";
import type { PICERLStage } from "@/types/caseTemplates";
import type { GeneratedLink } from "@/utils/linkTemplates";
import type { UIState } from "@/utils/statusHelpers";
import { ALERT_STATUS_LABELS } from "@/utils/statusLabels";
import type { LinkedAlertResolutionUpdate } from "@/hooks/useResolveLinkedAlerts";

import { ArrowRight, Check, CheckCircle, ChevronLeft, Columns3, Copy, Edit2, HelpCircle, Link, Link2Off, List, Network, SlidersHorizontal, Users, X, XCircle } from 'lucide-react';
// Unified status type that works for alerts, cases, and tasks (API format: UPPERCASE)
export type EntityStatus = AlertStatus | CaseStatus | TaskStatus;

// Entity type to determine UI behavior
export type EntityType = 'alert' | 'case' | 'task';
export type TimelineViewMode = 'timeline' | 'graph' | 'swimlane';

const TIMELINE_MODE_ITEM_CLASS_NAME = "min-w-0 flex-1 justify-center [&>span]:min-w-0 [&>span]:text-left";

function getSharedLabelIndex(keys: readonly string[], labelIndexes: Record<string, number>): number {
  return keys.reduce((sharedIndex, key) => Math.max(sharedIndex, labelIndexes[key] ?? 0), 0);
}

// Timeline filter types
export type SortOption = 'created_at' | 'timestamp';
export type SortDirection = 'asc' | 'desc';

interface LinkedCaseAlert {
  id: number;
  human_id: string;
  title: string;
  status: AlertStatus;
}

interface EntityHeaderRootProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "id"> {
  createdDate?: React.ReactNode;
  updatedDate?: React.ReactNode;
  id?: React.ReactNode;
  description?: React.ReactNode;
  // Entity type determines button labels and available actions
  entityType?: EntityType;
  // Entity state props (works for both alerts and cases)
  status?: EntityStatus;
  assignee?: string | null;
  priority?: PriorityType | null;
  // Case ID for alerts that have been escalated
  caseId?: number | null;
  // User data
  currentUser?: string | null;
  users?: any[];
  isLoadingUsers?: boolean;
  // Mutation state
  isUpdating?: boolean;
  presenceText?: string | null;
  // Mode: 'editable' shows full controls, 'readonly' is preview mode (assignment works, close/reopen hidden)
  mode?: 'editable' | 'readonly';
  // Callbacks
  onAssignToMe?: () => void;
  onAssignToUser?: (username: string) => void;
  onUnassign?: () => void;
  // onCloseAlert receives UIState (lowercase) values - caller should convert to API format
  onCloseAlert?: (status: UIState) => void;
  onCloseCaseWithDetails?: (payload: {
    alert_updates: LinkedAlertResolutionUpdate[];
    tags: string[];
    note?: string;
  }) => void;
  onReopenAlert?: () => void;
  onPrimaryAction?: () => void;
  triageRecommendation?: TriageRecommendationRead | null;
  onAcceptTriageRecommendation?: (options: AcceptRecommendationRequest) => void;
  onRejectTriageRecommendation?: (category: RejectionCategory, reason?: string) => void;
  isAcceptingRecommendation?: boolean;
  isRejectingRecommendation?: boolean;
  onLinkToCase?: () => void;
  onUnlinkFromCase?: () => void;
  onEdit?: () => void;
  // Timeline view toggle props
  showTimelineViewToggle?: boolean;
  timelineViewMode?: TimelineViewMode;
  onTimelineViewModeChange?: (viewMode: TimelineViewMode) => void;
  graphViewDisabled?: boolean;
  swimlaneViewDisabled?: boolean;
  // Timeline filter props
  showTimelineFilter?: boolean;
  timelineItems?: TimelineItem[];
  selectedType?: string;
  onTypeChange?: (type: string | undefined) => void;
  sortBy?: SortOption;
  sortDirection?: SortDirection;
  onSortChange?: (sortBy: SortOption, direction: SortDirection) => void;
  groupSimilar?: boolean;
  onGroupSimilarChange?: (enabled: boolean) => void;
  picerlStages?: PICERLStage[];
  selectedPICERLStage?: PICERLStage;
  onPICERLStageChange?: (stage: PICERLStage | undefined) => void;
  hasLinkedEntityCards?: boolean;
  onCollapseLinkedEntityCards?: () => void;
  onExpandLinkedEntityCards?: () => void;
  // Mobile back button
  showBackButton?: boolean;
  onBackClick?: () => void;
  // Scroll container ref for hiding/showing on mobile scroll
  scrollContainerRef?: RefObject<HTMLElement | null>;
  linkedCaseAlerts?: LinkedCaseAlert[];
  linkedTaskCount?: number;
  caseTags?: string[];
  customLinks?: GeneratedLink[];
  className?: string;
}

const EntityHeaderRoot = React.forwardRef<
  HTMLDivElement,
  EntityHeaderRootProps
>(function EntityHeaderRoot(
  {
    createdDate: _createdDate,
    updatedDate: _updatedDate,
    id,
    description,
    entityType = 'alert',
    status,
    assignee,
    priority: _priority,
    caseId,
    currentUser,
    users = [],
    isLoadingUsers = false,
    isUpdating = false,
    presenceText,
    mode = 'editable',
    onAssignToMe,
    onAssignToUser,
    onUnassign,
    onCloseAlert,
    onCloseCaseWithDetails,
    onReopenAlert,
    onPrimaryAction: onPrimaryAction,
    triageRecommendation,
    onAcceptTriageRecommendation,
    onRejectTriageRecommendation,
    isAcceptingRecommendation = false,
    isRejectingRecommendation = false,
    onLinkToCase,
    onUnlinkFromCase,
    onEdit,
    showTimelineViewToggle = false,
    timelineViewMode = 'timeline',
    onTimelineViewModeChange,
    graphViewDisabled = false,
    swimlaneViewDisabled = false,
    showTimelineFilter = false,
    timelineItems = [],
    selectedType,
    onTypeChange,
    sortBy = 'timestamp',
    sortDirection = 'asc',
    onSortChange,
    groupSimilar = false,
    onGroupSimilarChange,
    picerlStages = [],
    selectedPICERLStage,
    onPICERLStageChange,
    hasLinkedEntityCards = false,
    onCollapseLinkedEntityCards,
    onExpandLinkedEntityCards,
    showBackButton = false,
    onBackClick,
    scrollContainerRef: _scrollContainerRef,
    linkedCaseAlerts = [],
    linkedTaskCount = 0,
    caseTags = [],
    customLinks = [],
    className,
    ...otherProps
  }: EntityHeaderRootProps,
  ref
) {
  const { resolvedTheme } = useTheme();
  const { isMobile, isTablet } = useBreakpointContext();
  const isDarkTheme = resolvedTheme === "dark";

  const isAlert = entityType === 'alert';
  const isCase = entityType === 'case';
  const isTask = entityType === 'task';
  const isReadOnly = mode === 'readonly';
  const isEditable = mode === 'editable';
  const isCompactHeader = isMobile || isTablet;

  // Determine if entity is closed (works for alerts, cases, and tasks)
  // Status prop comes from API in UPPERCASE format
  const isClosed = status && (
    status === 'CLOSED' || // Case status
    status === 'DONE' || // Task status
    [
      "CLOSED_TP",
      "CLOSED_BP",
      "CLOSED_FP",
      "CLOSED_UNRESOLVED",
      "CLOSED_DUPLICATE",
    ].includes(status) // Alert statuses
  );

  const isEscalated = status === 'ESCALATED' || (isAlert && !!caseId);
  const [isCaseClosureModalOpen, setIsCaseClosureModalOpen] = React.useState(false);
  const [isTriageRejectDialogOpen, setIsTriageRejectDialogOpen] = React.useState(false);
  const showAssignmentControls = Boolean(onAssignToMe || onAssignToUser || onUnassign);

  const buttonSize = isCompactHeader ? "small" : "medium";
  const shouldShowTimelineViewToggle = showTimelineViewToggle && Boolean(onTimelineViewModeChange);
  const timelineModeLabelKeys = React.useMemo(() => ['timeline', 'graph', 'swimlane'], []);
  const [timelineModeLabelIndexes, setTimelineModeLabelIndexes] = React.useState<Record<string, number>>({});
  const timelineModeLabelIndex = getSharedLabelIndex(timelineModeLabelKeys, timelineModeLabelIndexes);
  const updateTimelineModeLabelIndex = React.useCallback((key: string, labelIndex: number) => {
    setTimelineModeLabelIndexes((current) => (
      current[key] === labelIndex ? current : { ...current, [key]: labelIndex }
    ));
  }, []);

  React.useEffect(() => {
    const resetAdaptiveLabelIndexes = () => {
      setTimelineModeLabelIndexes({});
    };

    window.addEventListener('resize', resetAdaptiveLabelIndexes);
    return () => window.removeEventListener('resize', resetAdaptiveLabelIndexes);
  }, []);

  // Determine button labels based on entity type
  const closeButtonLabel = isTask
    ? "Close Task"
    : isCase
      ? "Close Case..."
      : "Close Alert...";
  const reopenButtonLabel = isTask
    ? (buttonSize === "medium" ? "Re-Open Task" : "Re-Open")
    : isCase
      ? (buttonSize === "medium" ? "Re-Open Case" : "Re-Open")
      : (buttonSize === "medium" ? "Re-Open Alert" : "Re-Open");

  // In preview mode (readonly), hide close/reopen buttons but keep assignment
  // In editable mode, show all controls
  const showCloseReopenButtons = isEditable;

  // Determine if we should show the primary action button (Escalate/Open Case/Open Task)
  const showPrimaryAction = (isAlert && !isEscalated && !isClosed) || ((isCase || isTask) && isReadOnly);
  const showAiEscalationDecision = Boolean(
    isAlert &&
    !isEscalated &&
    !isClosed &&
    triageRecommendation?.status === 'PENDING' &&
    triageRecommendation.request_escalate_to_case &&
    onAcceptTriageRecommendation &&
    onRejectTriageRecommendation
  );
  const primaryActionLabel = isTask && isReadOnly
    ? "View Task"
    : isCase && isReadOnly
      ? "View Case"
      : (buttonSize === "medium" ? "Escalate to Case" : "Escalate");

  const handleAcceptAiEscalation = () => {
    onAcceptTriageRecommendation?.({
      apply_status: true,
      apply_priority: true,
      apply_assignee: true,
      apply_tags: true,
    });
  };

  const handleRejectAiEscalation = (category: RejectionCategory, reason?: string) => {
    onRejectTriageRecommendation?.(category, reason);
    onPrimaryAction?.();
  };

  const renderPresence = () => presenceText ? (
    <div className="flex max-w-[38rem] items-center gap-1.5 text-right text-caption-bold font-caption-bold text-subtext-color" aria-live="polite">
      <Users className="h-3.5 w-3.5 flex-none" />
      <span className="min-w-0 truncate">{presenceText}</span>
    </div>
  ) : null;

  const renderTimelineViewToggle = (variant: "desktop" | "compact") => {
    if (!shouldShowTimelineViewToggle) {
      return null;
    }

    return (
      <ToggleGroup
        value={timelineViewMode}
        variant="compact-button"
        className={cn(
          "max-w-full border border-neutral-border",
          variant === "compact" ? "w-full" : "w-80",
        )}
        onValueChange={(value: string) => {
          if (value === 'timeline' || value === 'graph' || value === 'swimlane') {
            onTimelineViewModeChange?.(value);
          }
        }}
      >
        <ToggleGroup.Item
          icon={<List />}
          value="timeline"
          aria-label="Timeline"
          tooltip={timelineModeLabelIndex > 0 ? "Timeline" : undefined}
          className={cn(TIMELINE_MODE_ITEM_CLASS_NAME, timelineModeLabelIndex >= 1 && "gap-0")}
        >
          <AdaptiveToggleLabel
            labels={['Timeline']}
            labelIndex={timelineModeLabelIndex}
            onLabelIndexChange={(labelIndex) => updateTimelineModeLabelIndex('timeline', labelIndex)}
            srLabel="Timeline"
          />
        </ToggleGroup.Item>
        <ToggleGroup.Item
          disabled={graphViewDisabled}
          icon={<Network />}
          value="graph"
          aria-label="Graph"
          tooltip={timelineModeLabelIndex > 0 ? "Graph" : undefined}
          className={cn(TIMELINE_MODE_ITEM_CLASS_NAME, timelineModeLabelIndex >= 1 && "gap-0")}
        >
          <AdaptiveToggleLabel
            labels={['Graph']}
            labelIndex={timelineModeLabelIndex}
            onLabelIndexChange={(labelIndex) => updateTimelineModeLabelIndex('graph', labelIndex)}
            srLabel="Graph"
          />
        </ToggleGroup.Item>
        <ToggleGroup.Item
          disabled={swimlaneViewDisabled}
          icon={<Columns3 />}
          value="swimlane"
          aria-label="Swimlane"
          tooltip={timelineModeLabelIndex > 0 ? "Swimlane" : undefined}
          className={cn(TIMELINE_MODE_ITEM_CLASS_NAME, timelineModeLabelIndex >= 1 && "gap-0")}
        >
          <AdaptiveToggleLabel
            labels={['Swimlane']}
            labelIndex={timelineModeLabelIndex}
            onLabelIndexChange={(labelIndex) => updateTimelineModeLabelIndex('swimlane', labelIndex)}
            srLabel="Swimlane"
          />
        </ToggleGroup.Item>
      </ToggleGroup>
    );
  };

  const renderTimelineFilter = (variant: "desktop" | "compact") => (
    showTimelineFilter && onSortChange && onTypeChange ? (
      <TimelineFilter
        items={timelineItems}
        selectedType={selectedType}
        onTypeChange={onTypeChange}
        sortBy={sortBy}
        sortDirection={sortDirection}
        onSortChange={onSortChange}
        groupSimilar={groupSimilar}
        onGroupSimilarChange={onGroupSimilarChange}
        picerlStages={picerlStages}
        selectedPICERLStage={selectedPICERLStage}
        onPICERLStageChange={onPICERLStageChange}
        hasLinkedEntityCards={hasLinkedEntityCards}
        onCollapseLinkedEntityCards={onCollapseLinkedEntityCards}
        onExpandLinkedEntityCards={onExpandLinkedEntityCards}
        buttonSize={variant === "desktop" ? "medium" : "small"}
        className={variant === "compact" ? "border-t-0 pt-0" : undefined}
        disabled={timelineItems.length === 0}
        rightContent={renderPresence()}
        leadingContent={renderTimelineViewToggle(variant)}
      />
    ) : null
  );

  const renderHeaderActions = (variant: "desktop" | "compact") => {
    const compact = variant === "compact";
    const controlButtonClassName = compact ? "h-8 w-full" : "h-auto w-auto flex-none self-stretch";
    const linkButtonClassName = compact ? "h-8 flex-1" : "h-auto w-auto flex-none self-stretch";
    const controlGroupClassName = compact
      ? "flex w-full min-w-0 items-center justify-stretch gap-2"
      : "flex flex-none items-center justify-end gap-2 self-stretch";
    const customLinksClassName = compact
      ? "flex w-full min-w-0 items-center justify-stretch gap-1"
      : "flex flex-none items-center justify-end gap-1 self-stretch";
    const actionsButtonSize = compact ? "small" : "medium";
    const actionsAssigneeSize = compact ? "small" : "medium";

    return (
      <div
        className={cn(
          "flex min-h-9 flex-wrap items-stretch justify-end gap-2",
          compact ? "w-full justify-stretch" : "flex",
        )}
      >
        {isAlert && isEscalated && onUnlinkFromCase && (
          <Button
            className={controlButtonClassName}
            variant="neutral-secondary"
            size={actionsButtonSize}
            icon={<Link2Off />}
            onClick={onUnlinkFromCase}
            disabled={isUpdating}
          >
            {compact ? "Unlink" : "Unlink from Case"}
          </Button>
        )}
        {customLinks.length > 0 ? (
          <div className={customLinksClassName}>
            {customLinks.map((link) => (
              <LinkButton
                key={link.id}
                href={link.url}
                icon={link.icon}
                tooltip={link.tooltip || link.name}
                size={actionsButtonSize}
                variant="brand-tertiary"
                className={linkButtonClassName}
              />
            ))}
          </div>
        ) : null}
        {showAssignmentControls && (
          <div className={controlGroupClassName}>
            <AssigneeSelector
              mode="assign"
              size={actionsAssigneeSize}
              className={actionsAssigneeSize === "medium" ? "h-auto w-auto flex-none self-stretch" : "h-8 w-full"}
              currentAssignee={assignee || null}
              currentUser={currentUser || null}
              users={users}
              isLoadingUsers={isLoadingUsers}
              disabled={isUpdating}
              onUnassign={onUnassign}
              onAssignToMe={onAssignToMe}
              onAssignToUser={onAssignToUser}
            />
          </div>
        )}
        {(showCloseReopenButtons || showPrimaryAction) && (
          <div className={controlGroupClassName}>
            {onEdit && (
              <Button
                className={controlButtonClassName}
                variant="neutral-secondary"
                size={actionsButtonSize}
                icon={<Edit2 />}
                onClick={onEdit}
                disabled={isUpdating}
              >
                Edit
              </Button>
            )}
            {showCloseReopenButtons && (
              <>
                {isClosed ? (
                  <Button
                    className={controlButtonClassName}
                    variant="brand-primary"
                    size={actionsButtonSize}
                    icon={<Check />}
                    onClick={onReopenAlert}
                    disabled={isUpdating}
                  >
                    {reopenButtonLabel}
                  </Button>
                ) : isCase ? (
                  <Button
                    className={controlButtonClassName}
                    variant="neutral-secondary"
                    size={actionsButtonSize}
                    icon={<X />}
                    disabled={isUpdating}
                    onClick={() => {
                      if (onCloseCaseWithDetails) {
                        setIsCaseClosureModalOpen(true);
                        return;
                      }
                      onCloseAlert?.("closed");
                    }}
                  >
                    {compact ? "Close" : closeButtonLabel}
                  </Button>
                ) : (
                  <DropdownMenuRoot modal={false}>
                    <DropdownMenuTrigger asChild={true}>
                      <Button
                        className={controlButtonClassName}
                        variant="neutral-secondary"
                        size={actionsButtonSize}
                        icon={<X />}
                        disabled={isUpdating}
                      >
                        {compact ? "Close" : closeButtonLabel}
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent side="bottom" align="start" sideOffset={4}>
                      {isAlert ? (
                        <>
                          <DropdownMenu.DropdownItem
                            icon={<Check />}
                            label={ALERT_STATUS_LABELS.CLOSED_TP}
                            onClick={() => onCloseAlert?.("closed_true_positive")}
                          />
                          <DropdownMenu.DropdownItem
                            icon={<CheckCircle />}
                            label={ALERT_STATUS_LABELS.CLOSED_BP}
                            onClick={() => onCloseAlert?.("closed_benign_positive")}
                          />
                          <DropdownMenu.DropdownItem
                            icon={<XCircle />}
                            label={ALERT_STATUS_LABELS.CLOSED_FP}
                            onClick={() => onCloseAlert?.("closed_false_positive")}
                          />
                          <DropdownMenu.DropdownItem
                            icon={<HelpCircle />}
                            label={ALERT_STATUS_LABELS.CLOSED_UNRESOLVED}
                            onClick={() => onCloseAlert?.("closed_unresolved")}
                          />
                          <DropdownMenu.DropdownItem
                            icon={<Copy />}
                            label={ALERT_STATUS_LABELS.CLOSED_DUPLICATE}
                            onClick={() => onCloseAlert?.("closed_duplicate")}
                          />
                        </>
                      ) : (
                        <DropdownMenu.DropdownItem
                          icon={<Check />}
                          label="Mark as Done"
                          onClick={() => onCloseAlert?.("tsk_done" as UIState)}
                        />
                      )}
                    </DropdownMenuContent>
                  </DropdownMenuRoot>
                )}
              </>
            )}
            {isAlert && !isEscalated && !isClosed && onLinkToCase && (
              <Button
                className={controlButtonClassName}
                variant="neutral-secondary"
                size={actionsButtonSize}
                icon={<Link />}
                onClick={onLinkToCase}
                disabled={isUpdating}
              >
                {compact ? "Link" : "Link to Case"}
              </Button>
            )}
            {showAiEscalationDecision ? (
              <>
                <Button
                  className={controlButtonClassName}
                  variant="destructive-secondary"
                  size={actionsButtonSize}
                  icon={<X />}
                  onClick={() => setIsTriageRejectDialogOpen(true)}
                  disabled={isUpdating || isAcceptingRecommendation || isRejectingRecommendation}
                  loading={isRejectingRecommendation}
                >
                  {compact ? "Reject AI" : "Escalate to Case (Reject AI)"}
                </Button>
                <Button
                  className={controlButtonClassName}
                  size={actionsButtonSize}
                  iconRight={<ArrowRight />}
                  onClick={handleAcceptAiEscalation}
                  disabled={isUpdating || isAcceptingRecommendation || isRejectingRecommendation}
                  loading={isAcceptingRecommendation}
                >
                  {compact ? "Accept AI" : "Escalate to Case (Accept AI)"}
                </Button>
              </>
            ) : showPrimaryAction && onPrimaryAction && (
              <Button
                className={controlButtonClassName}
                size={actionsButtonSize}
                iconRight={<ArrowRight />}
                onClick={onPrimaryAction}
                disabled={isUpdating}
              >
                {primaryActionLabel}
              </Button>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div
      className={cn("flex w-full flex-col flex-wrap items-center gap-2 mobile:gap-0", className)}
      ref={ref}
      {...otherProps}
    >
      <div className="flex w-full flex-wrap items-center gap-4 mobile:gap-2 ">
        <div className={cn(
          "flex grow shrink-0 basis-0 flex-col items-start gap-1",
          isCompactHeader ? "min-w-0" : "min-w-[288px]",
        )}>
          {/* Row with back button and ID/description block */}
          <div className="flex w-full items-start gap-2">
            {/* Mobile back button */}
            {showBackButton && onBackClick && (
              <div className="hidden mobile:flex">
                <IconButton
                  size="large"
                  icon={<ChevronLeft />}
                  onClick={onBackClick}
                  variant="neutral-primary"
                />
              </div>
            )}

            {/* ID and Description block */}
            <div className="flex flex-col gap-1 flex-1 mobile:gap-0">
              {id ? (
                <div className="w-full flex items-center gap-2">
                  <span className="text-heading-2 font-heading-2 text-default-font">
                    {id}
                  </span>
                </div>
              ) : null}

              {/* Description */}
              {description ? (
                <div className={isDarkTheme ? "w-full text-body font-body text-brand-primary" : "w-full text-body font-body text-black"}>
                  {description}
                </div>
              ) : null}
            </div>
          </div>

        </div>
        {!isCompactHeader ? renderHeaderActions("desktop") : null}
        {isCompactHeader ? (
          <DropdownMenuRoot modal={false}>
            <DropdownMenuTrigger asChild={true}>
              <IconButton
                className="ml-auto h-9 w-9 flex-none"
                icon={<SlidersHorizontal />}
                aria-label="Timeline controls"
                title="Timeline controls"
                variant="neutral-secondary"
              />
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="end"
              side="bottom"
              sideOffset={8}
              className="max-h-[min(36rem,calc(100vh-7rem))] w-[min(42rem,calc(100vw-2rem))] overflow-y-auto border border-neutral-border bg-default-background p-3 shadow-accent-1-shadow-sm"
            >
              <div className="flex min-w-0 flex-col gap-3">
                {renderHeaderActions("compact")}
                {renderTimelineFilter("compact")}
              </div>
            </DropdownMenuContent>
          </DropdownMenuRoot>
        ) : null}
      </div>
      {!isCompactHeader ? (
        <div className="w-full">
          {renderTimelineFilter("desktop")}
        </div>
      ) : null}

      {isCase && onCloseCaseWithDetails && (
        <CaseClosureModal
          open={isCaseClosureModalOpen}
          onOpenChange={setIsCaseClosureModalOpen}
          linkedAlerts={linkedCaseAlerts}
          linkedTaskCount={linkedTaskCount}
          initialTags={caseTags}
          isSubmitting={isUpdating}
          onConfirm={(payload) => {
            onCloseCaseWithDetails(payload);
            setIsCaseClosureModalOpen(false);
          }}
        />
      )}
      <TriageRejectionDialog
        open={showAiEscalationDecision && isTriageRejectDialogOpen}
        onOpenChange={setIsTriageRejectDialogOpen}
        onReject={handleRejectAiEscalation}
      />
    </div>
  );
});

export const EntityHeader = EntityHeaderRoot;
