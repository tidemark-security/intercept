"use client";

import React from "react";
import { useNavigate } from "react-router-dom";

import { Priority } from "@/components/misc/Priority";
import { State } from "@/components/misc/State";
import { TagsManager } from "@/components/forms/TagsManager";
import { Button } from "@/components/buttons/Button";
import { CopyableTimestamp } from "@/components/data-display/CopyableTimestamp";
import MarkdownContent from "@/components/data-display/MarkdownContent";
import { TimelineDescriptionBlock } from "@/components/timeline/TimelineDescriptionBlock";
import { useTheme } from "@/contexts/ThemeContext";
import { alertStatusToUIState, caseStatusToUIState, taskStatusToUIState, priorityToUIPriority } from "@/utils/statusHelpers";
import { getTaskDueStatus, type TaskDueStatus } from "@/utils/taskDueStatus";

import type { AlertRead } from "@/types/generated/models/AlertRead";
import type { CaseRead } from "@/types/generated/models/CaseRead";
import type { TaskRead } from "@/types/generated/models/TaskRead";
import type { AlertStatus } from "@/types/generated/models/AlertStatus";
import type { CaseStatus } from "@/types/generated/models/CaseStatus";
import type { TaskStatus } from "@/types/generated/models/TaskStatus";
import { cn } from "@/utils/cn";
import { convertNumericToHumanId } from "@/utils/caseHelpers";

import { ArrowRight, CalendarClock, ClockAlert, ClockPlus, RadioTower, User } from "lucide-react";

interface EntityMetadataCardProps {
  entity: AlertRead | CaseRead | TaskRead | null;
  entityType: "alert" | "case" | "task";
  isLoading?: boolean;
  onUpdateTags?: (tags: string[]) => void;
  showTags?: boolean;
}

export function EntityMetadataCard({ entity, entityType, isLoading, onUpdateTags, showTags = true }: EntityMetadataCardProps) {
  const navigate = useNavigate();
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark";
  const rootClassName = cn(
    "flex w-full flex-col gap-3",
    showTags && "border-b border-solid p-6 mobile:p-4",
    showTags && (isDarkTheme ? "border-brand-primary" : "border-neutral-1000"),
  );

  const currentTags = React.useMemo(() => {
    if (!entity) return [];
    const tags = entity.tags;
    if (!tags) return [];
    return Array.isArray(tags) ? tags : [];
  }, [entity]);

  if (isLoading) {
    return (
      <div className={rootClassName}>
        <div className="flex h-7 w-full animate-pulse rounded bg-neutral-200" />
        <div className="grid w-full gap-2 md:grid-cols-3">
          <div className="h-14 animate-pulse rounded-md bg-neutral-200" />
          <div className="h-14 animate-pulse rounded-md bg-neutral-200" />
          <div className="h-14 animate-pulse rounded-md bg-neutral-200" />
        </div>
      </div>
    );
  }

  if (!entity) {
    return (
      <div className={cn(rootClassName, "items-start")}>
        <span className="text-body font-body text-subtext-color">
          No {entityType} selected
        </span>
      </div>
    );
  }

  const isAlert = entityType === "alert";
  const isTask = entityType === "task";
  const alertEntity = isAlert ? (entity as AlertRead) : null;
  const caseEntity = entityType === "case" ? (entity as CaseRead) : null;
  const taskEntity = isTask ? (entity as TaskRead) : null;

  let statusValue: React.ComponentProps<typeof State>["state"];
  if (isAlert) {
    statusValue = alertStatusToUIState(entity.status as AlertStatus) as React.ComponentProps<typeof State>["state"];
  } else if (isTask) {
    statusValue = taskStatusToUIState(entity.status as TaskStatus) as React.ComponentProps<typeof State>["state"];
  } else {
    statusValue = caseStatusToUIState(entity.status as CaseStatus) as React.ComponentProps<typeof State>["state"];
  }

  const InfoTile = ({
    icon,
    label,
    children,
    className,
    dueStatus,
  }: {
    icon: React.ReactNode;
    label: string;
    children: React.ReactNode;
    className?: string;
    dueStatus?: TaskDueStatus;
  }) => (
    <div
      className={cn(
        "flex min-w-0 items-start gap-2 rounded-md px-2.5 py-2",
        dueStatus === 'overdue'
          ? "border border-solid border-error-500 bg-error-50"
          : dueStatus === 'due_soon'
            ? "border border-solid border-warning-500 bg-warning-50"
            : "bg-neutral-200",
        className,
      )}
    >
      <span
        className={cn(
          "mt-0.5 flex-none text-subtext-color",
          dueStatus === 'overdue' && "text-error-1000",
          dueStatus === 'due_soon' && "text-warning-1000",
        )}
      >
        {icon}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span
          className={cn(
            "text-[11px] font-medium uppercase tracking-wide text-subtext-color",
            dueStatus === 'overdue' && "text-error-1000",
            dueStatus === 'due_soon' && "text-warning-1000",
          )}
        >
          {label}
        </span>
        {children}
      </div>
    </div>
  );

  const TimestampField = ({ label, value, icon, dueStatus }: { label: string; value: string | null | undefined; icon: React.ReactNode; dueStatus?: TaskDueStatus }) => {
    if (!value) {
      return null;
    }

    const timestampTextClassName = dueStatus === 'overdue'
      ? 'text-error-1000'
      : dueStatus === 'due_soon'
        ? 'text-warning-1000'
        : undefined;

    return (
      <InfoTile icon={icon} label={label} className={detailFieldClassName} dueStatus={dueStatus}>
        <CopyableTimestamp
          value={value}
          showFull
          variant="default-right"
          className="min-w-0 max-w-full flex-wrap"
          textClassName={timestampTextClassName}
        />
      </InfoTile>
    );
  };

  const summaryFieldClassName = "flex min-w-[min(100%,14rem)] flex-1 basis-56 flex-col gap-1 rounded-md border border-solid border-neutral-border bg-default-background px-2.5 py-2";
  const detailFieldClassName = "min-w-[min(100%,18rem)] flex-1 basis-72";

  const PersonField = ({ label, value }: { label: string; value: string | null | undefined }) => (
    <div className={summaryFieldClassName}>
      <span className="text-[11px] font-medium uppercase tracking-wide text-subtext-color">
        {label}
      </span>
      <div className="flex h-6 w-full min-w-0 items-center gap-1.5 rounded-md bg-neutral-200 px-2">
        <User className="h-3.5 w-3.5 flex-none text-subtext-color" />
        <span className="min-w-0 truncate text-caption font-caption text-default-font">
          {value || "Unassigned"}
        </span>
      </div>
    </div>
  );

  const createdByValue = caseEntity?.created_by || taskEntity?.created_by || (alertEntity as (AlertRead & { created_by?: string | null }) | null)?.created_by;
  const sourceValue = alertEntity?.source;
  const taskDueStatus = getTaskDueStatus(taskEntity?.due_date, taskEntity?.status);
  const taskDueLabel = taskDueStatus === 'overdue'
    ? 'Overdue'
    : taskDueStatus === 'due_soon'
      ? 'Due Soon'
      : 'Due';
  const relatedCaseId = alertEntity?.case_id || taskEntity?.case_id;
  const relatedCaseHref = relatedCaseId ? `/cases/${convertNumericToHumanId(relatedCaseId)}` : null;
  const shouldRenderStandaloneTagRow = showTags && (currentTags.length > 0 || !!onUpdateTags);
  const parentCaseAction = showTags && relatedCaseHref ? (
    <div className="ml-auto flex items-center gap-2">
      <Button
        variant="neutral-tertiary"
        size="small"
        onClick={() => navigate(relatedCaseHref)}
        iconRight={<ArrowRight className="h-3.5 w-3.5" />}
      >
        Open Parent Case
      </Button>
    </div>
  ) : null;
  const shouldRenderStandaloneFooter = !!entity.description || shouldRenderStandaloneTagRow || !!parentCaseAction;

  return (
    <div className={rootClassName}>
      <div className="flex w-full flex-wrap gap-2">
        <div className={summaryFieldClassName}>
          <span className="text-[11px] font-medium uppercase tracking-wide text-subtext-color">
            Status
          </span>
          <State state={statusValue} className="w-full" />
        </div>

        <div className={summaryFieldClassName}>
          <span className="text-[11px] font-medium uppercase tracking-wide text-subtext-color">
            Priority
          </span>
          {entity.priority ? (
            <Priority priority={priorityToUIPriority(entity.priority)} className="w-full" />
          ) : (
            <span className="text-body font-body text-subtext-color">
              Not set
            </span>
          )}
        </div>

        <PersonField label="Assignee" value={entity.assignee} />
        <PersonField label="Created By" value={createdByValue} />
      </div>

      <div className="flex w-full flex-wrap gap-2">
        {isTask && taskEntity?.due_date ? (
          <TimestampField label={taskDueLabel} value={taskEntity.due_date} icon={<CalendarClock className="h-3.5 w-3.5" />} dueStatus={taskDueStatus} />
        ) : null}

        <TimestampField label="Created" value={entity.created_at} icon={<ClockPlus className="h-3.5 w-3.5" />} />
        <TimestampField label="Updated" value={entity.updated_at} icon={<ClockAlert className="h-3.5 w-3.5" />} />

        {!isAlert && !isTask && caseEntity?.closed_at ? (
          <TimestampField label="Closed" value={caseEntity.closed_at} icon={<ClockAlert className="h-3.5 w-3.5" />} />
        ) : null}

        {sourceValue ? (
          <InfoTile icon={<RadioTower className="h-3.5 w-3.5" />} label="Source" className={detailFieldClassName}>
            <span className="min-w-0 truncate text-body font-body text-default-font">
              {sourceValue}
            </span>
          </InfoTile>
        ) : null}

      </div>

      {shouldRenderStandaloneFooter ? (
        <TimelineDescriptionBlock
          variant={showTags ? "metadata" : "timeline"}
          actionButtons={parentCaseAction}
          tagContent={shouldRenderStandaloneTagRow ? (
            <TagsManager
              tags={currentTags}
              onTagsChange={onUpdateTags || (() => {})}
              label="Tags"
              inline={true}
              readonly={!onUpdateTags}
              placeholder={onUpdateTags ? "+ Add tags" : (currentTags.length > 0 ? " " : "No tags")}
              className={!onUpdateTags ? "pointer-events-none opacity-60" : ""}
            />
          ) : null}
        >
          {entity.description ? (
            <MarkdownContent content={entity.description} />
          ) : null}
        </TimelineDescriptionBlock>
      ) : null}
    </div>
  );
}