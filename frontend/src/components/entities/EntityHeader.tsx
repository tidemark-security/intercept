"use client";

import React, { useMemo, RefObject } from "react";
import { useScrollHide } from "@/hooks/useScrollHide";
import { useTheme } from "@/contexts/ThemeContext";
// import { cn } from "@/utils/cn";
import { Button } from "@/components/buttons/Button";
import { IconButton } from "@/components/buttons/IconButton";
import { DropdownMenu, DropdownMenuRoot, DropdownMenuTrigger, DropdownMenuContent } from "@/components/overlays/DropdownMenu";
import { ToggleGroup } from "@/components/buttons/ToggleGroup";
import { Priority } from "@/components/misc/Priority";
import { AssigneeSelector } from "@/components/forms/AssigneeSelector";
import { TimelineFilter } from "@/components/timeline/TimelineFilter";
import { CaseClosureModal } from "@/components/entities/CaseClosureModal";

import type { AlertStatus } from "@/types/generated/models/AlertStatus";
import type { CaseStatus } from "@/types/generated/models/CaseStatus";
import type { TaskStatus } from "@/types/generated/models/TaskStatus";
import type { Priority as PriorityType } from "@/types/generated/models/Priority";
import type { TimelineItem } from "@/types/timeline";
import type { UIState } from "@/utils/statusHelpers";

import { ArrowRight, ArrowUp, Check, CheckCircle, ChevronLeft, Copy, Edit2, HelpCircle, Link, Link2Off, X, XCircle } from 'lucide-react';
// Unified status type that works for alerts, cases, and tasks (API format: UPPERCASE)
export type EntityStatus = AlertStatus | CaseStatus | TaskStatus;

// Entity type to determine UI behavior
export type EntityType = 'alert' | 'case' | 'task';

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
  // Mode: 'editable' shows full controls, 'readonly' is preview mode (assignment works, close/reopen hidden)
  mode?: 'editable' | 'readonly';
  // Callbacks
  onAssignToMe?: () => void;
  onAssignToUser?: (username: string) => void;
  onUnassign?: () => void;
  // onCloseAlert receives UIState (lowercase) values - caller should convert to API format
  onCloseAlert?: (status: UIState) => void;
  onCloseCaseWithDetails?: (payload: {
    alert_closure_updates: Array<{ alert_id: number; status: AlertStatus }>;
    tags: string[];
  }) => void;
  onReopenAlert?: () => void;
  onPrimaryAction?: () => void;
  onLinkToCase?: () => void;
  onUnlinkFromCase?: () => void;
  onEdit?: () => void;
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
  // Mobile back button
  showBackButton?: boolean;
  onBackClick?: () => void;
  // Scroll container ref for hiding/showing on mobile scroll
  scrollContainerRef?: RefObject<HTMLElement | null>;
  linkedCaseAlerts?: LinkedCaseAlert[];
  linkedTaskCount?: number;
  caseTags?: string[];
  className?: string;
}

const EntityHeaderRoot = React.forwardRef<
  HTMLDivElement,
  EntityHeaderRootProps
>(function EntityHeaderRoot(
  {
    createdDate,
    updatedDate,
    id,
    description,
    entityType = 'alert',
    status,
    assignee,
    priority,
    caseId,
    currentUser,
    users = [],
    isLoadingUsers = false,
    isUpdating = false,
    mode = 'editable',
    onAssignToMe,
    onAssignToUser,
    onUnassign,
    onCloseAlert,
    onCloseCaseWithDetails,
    onReopenAlert,
    onPrimaryAction: onPrimaryAction,
    onLinkToCase,
    onUnlinkFromCase,
    onEdit,
    showTimelineFilter = false,
    timelineItems = [],
    selectedType,
    onTypeChange,
    sortBy = 'timestamp',
    sortDirection = 'asc',
    onSortChange,
    groupSimilar = true,
    onGroupSimilarChange,
    showBackButton = false,
    onBackClick,
    scrollContainerRef,
    linkedCaseAlerts = [],
    linkedTaskCount = 0,
    caseTags = [],
    className,
    ...otherProps
  }: EntityHeaderRootProps,
  ref
) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark";

  const isAlert = entityType === 'alert';
  const isCase = entityType === 'case';
  const isTask = entityType === 'task';
  const isReadOnly = mode === 'readonly';
  const isEditable = mode === 'editable';

  // Hook for hiding header elements on scroll (mobile only)
  const { isVisible } = useScrollHide({
    scrollContainerRef: scrollContainerRef || { current: null },
    threshold: 10,
    mobileOnly: true,
  });

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

  // Detect mobile screen size
  const [isMobile, setIsMobile] = React.useState(false);

  React.useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const buttonSize = isMobile ? "small" : "medium";
  const assigneeSize = isMobile ? "small" : "medium";

  // Determine button labels based on entity type
  const closeButtonLabel = isTask 
    ? "Close Task" 
    : isCase 
      ? "Close Case" 
      : "Close Alert";
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
  const primaryActionLabel = isTask && isReadOnly
    ? "View Task"
    : isCase && isReadOnly
      ? "View Case"
      : (buttonSize === "medium" ? "Escalate to Case" : "Escalate");

  return (
    <div
      className={"flex w-full flex-col flex-wrap items-center gap-2 mobile:gap-0"}
      ref={ref}
      {...otherProps}
    >
      <div className="flex w-full flex-wrap items-center gap-4 mobile:gap-2 ">
        <div className="flex min-w-[288px] grow shrink-0 basis-0 flex-col items-start gap-1 ">
          {/* Row with back button and ID/description block */}
          <div className={`flex w-full items-start gap-2 mobile:border-b mobile:border-solid mobile:border-neutral-border mobile:pb-2 mobile:transition-all mobile:duration-300 ${!isVisible ? 'mobile:border-transparent mobile:pb-0' : ''}`}>
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
        {/* Action Buttons */}
        <div className={`flex h-9 mobile:h-8 items-center justify-end gap-2 mobile:w-full mobile:justify-stretch mobile:transition-all mobile:duration-300 ${!isVisible ? 'mobile:opacity-0 mobile:pointer-events-none mobile:h-0 mobile:overflow-hidden' : 'mobile:opacity-100'}`}>
          {/* Unlink from Case button - shown for escalated alerts */}
          {isAlert && isEscalated && onUnlinkFromCase && (
            <Button
              className={buttonSize === "medium" ? "h-auto w-auto flex-none self-stretch" : "h-8 w-full"}
              variant="neutral-secondary"
              size={buttonSize}
              icon={<Link2Off />}
              onClick={onUnlinkFromCase}
              disabled={isUpdating}
            >
              {buttonSize === "medium" ? "Unlink from Case" : "Unlink"}
            </Button>
          )}
          {/* Assignee Selector - Always shown and functional */}
          <div className="flex items-center justify-end gap-2 self-stretch mobile:flex-1">
            <AssigneeSelector
              mode="assign"
              size={assigneeSize}
              className={assigneeSize === "medium" ? "h-auto w-auto flex-none self-stretch" : "h-8 w-full"}
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
          {/* Close/Reopen and Primary Action Buttons - Only in editable mode or for primary action in preview */}
          {(showCloseReopenButtons || showPrimaryAction) && (
            <div className="flex items-center justify-end gap-2 self-stretch mobile:flex-1">
              {onEdit && (
                <Button
                  className={buttonSize === "medium" ? "h-auto w-auto flex-none self-stretch" : "h-8 w-full"}
                  variant="neutral-secondary"
                  size={buttonSize}
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
                      className={buttonSize === "medium" ? "h-auto w-auto flex-none self-stretch" : "h-8 w-full"}
                      variant="brand-primary"
                      size={buttonSize}
                      icon={<Check />}
                      onClick={onReopenAlert}
                      disabled={isUpdating}
                    >
                      {reopenButtonLabel}
                    </Button>
                  ) : (
                    <DropdownMenuRoot>
                      <DropdownMenuTrigger asChild={true}>
                        <Button
                          className={buttonSize === "medium" ? "h-auto w-auto flex-none self-stretch" : "h-8 w-full"}
                          variant="neutral-secondary"
                          size={buttonSize}
                          icon={<X />}
                          disabled={isUpdating}
                        >
                          {buttonSize === "medium" ? closeButtonLabel : "Close"}
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent
                          side="bottom"
                          align="start"
                          sideOffset={4}
                        >
                            {isAlert ? (
                              <>
                                <DropdownMenu.DropdownItem
                                  icon={<Check />}
                                  label="True Positive"
                                  onClick={() => onCloseAlert?.("closed_true_positive")}
                                />
                                <DropdownMenu.DropdownItem
                                  icon={<CheckCircle />}
                                  label="True Positive Benign"
                                  onClick={() => onCloseAlert?.("closed_benign_positive")}
                                />
                                <DropdownMenu.DropdownItem
                                  icon={<XCircle />}
                                  label="False Positive"
                                  onClick={() => onCloseAlert?.("closed_false_positive")}
                                />
                                <DropdownMenu.DropdownItem
                                  icon={<HelpCircle />}
                                  label="Unresolved"
                                  onClick={() => onCloseAlert?.("closed_unresolved")}
                                />
                                <DropdownMenu.DropdownItem
                                  icon={<Copy />}
                                  label="Duplicate"
                                  onClick={() => onCloseAlert?.("closed_duplicate")}
                                />
                              </>
                            ) : isTask ? (
                              <DropdownMenu.DropdownItem
                                icon={<Check />}
                                label="Mark as Done"
                                onClick={() => onCloseAlert?.("tsk_done" as UIState)}
                              />
                            ) : (
                              <DropdownMenu.DropdownItem
                                icon={<X />}
                                label="Close Case"
                                onClick={() => {
                                  if (onCloseCaseWithDetails) {
                                    setIsCaseClosureModalOpen(true);
                                    return;
                                  }
                                  onCloseAlert?.("closed");
                                }}
                              />
                            )}
                        </DropdownMenuContent>
                    </DropdownMenuRoot>
                  )}
                </>
              )}
              {isAlert && !isEscalated && !isClosed && onLinkToCase && (
                <Button
                  className={buttonSize === "medium" ? "h-auto w-auto flex-none self-stretch" : "h-8 w-full"}
                  variant="neutral-secondary"
                  size={buttonSize}
                  icon={<Link />}
                  onClick={onLinkToCase}
                  disabled={isUpdating}
                >
                  {buttonSize === "medium" ? "Link to Case" : "Link"}
                </Button>
              )}
              {showPrimaryAction && onPrimaryAction && (
                <Button
                  className={buttonSize === "medium" ? "h-auto w-auto flex-none self-stretch" : "h-8 w-full"}
                  size={buttonSize}
                  iconRight={<ArrowRight />}
                  onClick={onPrimaryAction}
                >
                  {primaryActionLabel}
                </Button>
              )}
            </div>
          )}
        </div>
      </div>
      <div className="hidden desktop:flex w-full items-start gap-4">
        {createdDate ? (
          <span className="text-caption-bold font-caption-bold text-subtext-color">
            {createdDate}
          </span>
        ) : null}
        {updatedDate ? (
          <span className="text-caption-bold font-caption-bold text-subtext-color">
            {updatedDate}
          </span>
        ) : null}
      </div>
      
      {/* Timeline Filter - Only shown when showTimelineFilter is true */}
      {showTimelineFilter && onSortChange && onTypeChange && (
        <div className={`w-full mobile:transition-all mobile:duration-300 ${!isVisible ? 'mobile:opacity-0 mobile:pointer-events-none mobile:h-0 mobile:overflow-hidden' : 'mobile:opacity-100'}`}>
          <TimelineFilter
            items={timelineItems}
            selectedType={selectedType}
            onTypeChange={onTypeChange}
            sortBy={sortBy}
            sortDirection={sortDirection}
            onSortChange={onSortChange}
            groupSimilar={groupSimilar}
            onGroupSimilarChange={onGroupSimilarChange}
            buttonSize={buttonSize === "medium" ? "medium" : "small"}
            disabled={timelineItems.length === 0}
          />
        </div>
      )}

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
    </div>
  );
});

export const EntityHeader = EntityHeaderRoot;
