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

export type EntityMetadataCardVariant = "detail" | "timeline" | "compact";

interface EntityMetadataCardProps {
  entity: AlertRead | CaseRead | TaskRead | null;
  entityType: "alert" | "case" | "task";
  isLoading?: boolean;
  onUpdateTags?: (tags: string[]) => void;
  showTags?: boolean;
  variant?: EntityMetadataCardVariant;
}

export function EntityMetadataCard({
  entity,
  entityType,
  isLoading,
  onUpdateTags,
  showTags = true,
  variant,
}: EntityMetadataCardProps) {
  const navigate = useNavigate();
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark";
  const resolvedVariant = variant ?? (showTags ? "detail" : "timeline");
  const isTimelineVariant = resolvedVariant === "timeline";
  const isCompactVariant = resolvedVariant === "compact";
  const rootClassName = cn(
    "flex w-full min-w-0 flex-col",
    isTimelineVariant ? "gap-3" : "gap-4",
    isCompactVariant && "gap-2",
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
        <div className="flex h-8 w-full animate-pulse bg-neutral-200" />
        <div className="grid w-full gap-3 md:grid-cols-4">
          <div className="h-12 animate-pulse bg-neutral-200" />
          <div className="h-12 animate-pulse bg-neutral-200" />
          <div className="h-12 animate-pulse bg-neutral-200" />
          <div className="h-12 animate-pulse bg-neutral-200" />
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

  const MetaField = ({
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
        "group flex min-w-0 items-start gap-2 border-l border-solid border-neutral-border pl-3",
        dueStatus === 'overdue'
          ? "border-l-error-600 bg-error-50/40 pr-2 py-1.5"
          : dueStatus === 'due_soon'
            ? "border-l-warning-600 bg-warning-50/40 pr-2 py-1.5"
            : null,
        isCompactVariant ? "gap-1.5 pl-2" : "py-1",
        className,
      )}
    >
      <span
        className={cn(
          "mt-0.5 flex-none text-subtext-color transition-colors group-hover:text-default-font",
          dueStatus === 'overdue' && "text-error-1000",
          dueStatus === 'due_soon' && "text-warning-1000",
        )}
      >
        {icon}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span
          className={cn(
            "font-monospace-body text-[10px] font-medium uppercase leading-none tracking-normal text-subtext-color",
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
      <MetaField icon={icon} label={label} className={detailFieldClassName} dueStatus={dueStatus}>
        <CopyableTimestamp
          value={value}
          showFull
          variant="default-right"
          className="min-w-0 max-w-full flex-wrap font-monospace-body text-[11px] leading-4"
          textClassName={cn("text-default-font", timestampTextClassName)}
        />
      </MetaField>
    );
  };

  const summaryGridClassName = cn(
    "grid w-full min-w-0 gap-x-3 gap-y-4",
    isTimelineVariant
      ? "grid-cols-[repeat(auto-fit,minmax(min(100%,11rem),1fr))]"
      : "grid-cols-[repeat(auto-fit,minmax(min(100%,13rem),1fr))]",
    isCompactVariant && "gap-y-2",
  );
  const detailGridClassName = cn(
    "grid w-full min-w-0 border-t border-solid border-neutral-border/70 pt-3",
    isTimelineVariant
      ? "grid-cols-[repeat(auto-fit,minmax(min(100%,13rem),1fr))] gap-x-3 gap-y-3"
      : "grid-cols-[repeat(auto-fit,minmax(min(100%,16rem),1fr))] gap-x-4 gap-y-3",
    isCompactVariant && "pt-2",
  );
  const detailFieldClassName = "min-w-0";

  const PersonField = ({ label, value }: { label: string; value: string | null | undefined }) => (
    <MetaField icon={<User className="h-3.5 w-3.5" />} label={label}>
      <div className="flex min-h-5 w-full min-w-0 items-center">
        <span className="min-w-0 truncate text-caption-bold font-caption-bold text-default-font">
          {value || "Unassigned"}
        </span>
      </div>
    </MetaField>
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

  if (isCompactVariant) {
    return (
      <div className={rootClassName}>
        <div className="flex w-full min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <State state={statusValue} className="min-h-5 flex-none" />
          {entity.priority ? (
            <Priority priority={priorityToUIPriority(entity.priority)} className="min-h-5 flex-none" />
          ) : null}
          {entity.assignee ? (
            <span className="flex h-6 min-w-0 max-w-44 flex-none items-center justify-center gap-1 rounded-md border border-solid border-neutral-border bg-neutral-50 px-2">
              <User className="h-3.5 w-3.5 flex-none text-neutral-700" />
              <span className="min-w-0 grow shrink-0 basis-0 truncate text-center text-caption font-caption text-neutral-700">
                {entity.assignee}
              </span>
            </span>
          ) : null}
          {entity.updated_at || entity.created_at ? (
            <CopyableTimestamp
              value={entity.updated_at || entity.created_at}
              showFull={false}
              variant="default-right"
              className="min-w-0 max-w-full flex-wrap"
              textClassName="text-subtext-color"
            />
          ) : null}
        </div>

        {entity.description ? (
          <div className="w-full min-w-0 border-t border-solid border-neutral-border/70 pt-2">
            <MarkdownContent
              content={entity.description}
              className="line-clamp-2 text-caption font-caption leading-5 text-subtext-color [overflow-wrap:anywhere] [&_*]:text-inherit [&_p]:!my-0 [&_p]:inline"
            />
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className={rootClassName}>
      <div className={summaryGridClassName}>
        <MetaField label="Status" icon={null}>
          <State
            state={statusValue}
            className={cn("w-full", isTimelineVariant && "min-h-6")}
          />
        </MetaField>

        <MetaField label="Priority" icon={null}>
          {entity.priority ? (
            <Priority priority={priorityToUIPriority(entity.priority)} className="w-full" />
          ) : (
            <span className="text-body font-body text-subtext-color">
              Not set
            </span>
          )}
        </MetaField>

        <PersonField label="Assignee" value={entity.assignee} />
        <PersonField label="Created By" value={createdByValue} />
      </div>

      <div className={detailGridClassName}>
        {isTask && taskEntity?.due_date ? (
          <TimestampField label={taskDueLabel} value={taskEntity.due_date} icon={<CalendarClock className="h-3.5 w-3.5" />} dueStatus={taskDueStatus} />
        ) : null}

        <TimestampField label="Created" value={entity.created_at} icon={<ClockPlus className="h-3.5 w-3.5" />} />
        <TimestampField label="Updated" value={entity.updated_at} icon={<ClockAlert className="h-3.5 w-3.5" />} />

        {!isAlert && !isTask && caseEntity?.closed_at ? (
          <TimestampField label="Closed" value={caseEntity.closed_at} icon={<ClockAlert className="h-3.5 w-3.5" />} />
        ) : null}

        {sourceValue ? (
          <MetaField icon={<RadioTower className="h-3.5 w-3.5" />} label="Source" className={detailFieldClassName}>
            <span className="min-w-0 truncate text-caption-bold font-caption-bold text-default-font">
              {sourceValue}
            </span>
          </MetaField>
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
