"use client";

import React from "react";
import { useNavigate } from "react-router-dom";
import { QueueSearchText } from "@/components/search/QueueSearchHighlight";

import { PicerlStage } from "@/components/misc/PicerlStage";
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

import { Activity, ArrowRight, CalendarClock, ClockAlert, ClockPlus, Flag, RadioTower, Tags, User } from "lucide-react";

import { EntityDescription } from "./EntityDescription";
import styles from "./EntityMetadataCard.module.css";

export type EntityMetadataCardVariant = "detail" | "timeline" | "compact";

interface EntityMetadataCardProps {
  entity: AlertRead | CaseRead | TaskRead | null;
  entityType: "alert" | "case" | "task";
  isLoading?: boolean;
  onUpdateTags?: (tags: string[]) => void;
  beforeDescription?: React.ReactNode;
  showTags?: boolean;
  variant?: EntityMetadataCardVariant;
}

function MetaField({
  icon,
  label,
  children,
  dueStatus,
}: {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
  dueStatus?: TaskDueStatus;
}) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark";
  const hasDueStatus = dueStatus === "overdue" || dueStatus === "due_soon";

  return (
    <div
      className={cn(
        styles.field,
        "group flex min-w-0 items-start gap-2 border-l border-solid border-neutral-border py-1 pl-3",
        hasDueStatus && styles.dueField,
        dueStatus === 'overdue'
          ? cn(
            "border-l border-l-error-600 py-1.5 pr-2",
            isDarkTheme ? "bg-error-1000" : "bg-error-50/40",
          )
          : dueStatus === 'due_soon'
            ? cn(
              "border-l border-l-warning-600 py-1.5 pr-2",
              isDarkTheme ? "bg-warning-1100" : "bg-warning-50/40",
            )
            : null,
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "mt-0.5 flex-none text-subtext-color transition-colors group-hover:text-default-font",
          styles.fieldIcon,
          dueStatus === 'overdue' && (isDarkTheme ? "text-error-500" : "text-error-1000"),
          dueStatus === 'due_soon' && (isDarkTheme ? "text-warning-400" : "text-warning-1000"),
        )}
      >
        {icon}
      </span>
      <div className={cn("flex min-w-0 flex-1 flex-col gap-1", styles.fieldContent)}>
        <span
          className={cn(
            "font-monospace-body text-[10px] font-medium uppercase leading-none tracking-normal text-subtext-color",
            dueStatus === 'overdue' && (isDarkTheme ? "text-error-500" : "text-error-1000"),
            dueStatus === 'due_soon' && (isDarkTheme ? "text-warning-400" : "text-warning-1000"),
          )}
        >
          {label}
        </span>
        {children}
      </div>
    </div>
  );
}

function TimestampField({ label, value, icon, dueStatus }: {
  label: string;
  value: string | null | undefined;
  icon: React.ReactNode;
  dueStatus?: TaskDueStatus;
}) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark";
  if (!value) {
    return null;
  }

  const timestampTextClassName = dueStatus === 'overdue'
    ? isDarkTheme ? 'text-error-400' : 'text-error-1000'
    : dueStatus === 'due_soon'
      ? isDarkTheme ? 'text-warning-300' : 'text-warning-1000'
      : undefined;

  return (
    <MetaField icon={icon} label={label} dueStatus={dueStatus}>
      <CopyableTimestamp
        value={value}
        showFull
        variant="default-right"
        className="min-w-0 max-w-full flex-wrap font-monospace-body text-[11px] leading-4 [overflow-wrap:anywhere] [&>span]:min-w-0"
        textClassName={cn("text-default-font", timestampTextClassName)}
      />
    </MetaField>
  );
}

export function EntityMetadataCard({
  entity,
  entityType,
  isLoading,
  onUpdateTags,
  beforeDescription,
  showTags = true,
  variant,
}: EntityMetadataCardProps) {
  const navigate = useNavigate();
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark";
  const resolvedVariant = variant ?? (showTags ? "detail" : "timeline");
  const isDetailVariant = resolvedVariant === "detail";
  const isCompactVariant = resolvedVariant === "compact";
  const rootClassName = cn(
    "flex w-full min-w-0 flex-col",
    isCompactVariant ? "gap-2" : "gap-3",
    !isCompactVariant && styles.card,
    isDetailVariant && cn(
      "rounded-md border border-solid border-neutral-border px-4 py-3",
      isDarkTheme ? "bg-neutral-0" : "bg-neutral-50",
    ),
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
  const description = entity.description;
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

  const createdByValue = caseEntity?.created_by || taskEntity?.created_by;
  const sourceValue = alertEntity?.source;
  const taskDueStatus = getTaskDueStatus(taskEntity?.due_date, taskEntity?.status);
  const taskPICERLStage = taskEntity?.picerl_stage;
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
        {isAlert ? "Open Linked Case" : "Open Parent Case"}
      </Button>
    </div>
  ) : null;

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
                <QueueSearchText>{entity.assignee}</QueueSearchText>
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

        {description ? (
          <div className="w-full min-w-0 border-t border-solid border-neutral-border/70 pt-2">
            <MarkdownContent
              content={description}
              className="line-clamp-2 text-caption font-caption leading-5 text-subtext-color [overflow-wrap:anywhere] [&_*]:text-inherit [&_p]:!my-0 [&_p]:inline"
            />
          </div>
        ) : null}
      </div>
    );
  }

  const assigneeField = (
    <MetaField icon={<User className="h-3.5 w-3.5" />} label="Assignee">
      <span className="min-w-0 break-words text-caption-bold font-caption-bold text-default-font">
        <QueueSearchText>{entity.assignee || "Unassigned"}</QueueSearchText>
      </span>
    </MetaField>
  );
  const creatorField = !isAlert && (
    <MetaField icon={<User className="h-3.5 w-3.5" />} label="Created By">
      <span className="min-w-0 break-words text-caption-bold font-caption-bold text-default-font">
        <QueueSearchText>{createdByValue || "Not recorded"}</QueueSearchText>
      </span>
    </MetaField>
  );
  const sourceField = sourceValue && (
    <MetaField icon={<RadioTower className="h-3.5 w-3.5" />} label="Source">
      <span className="min-w-0 break-words text-caption-bold font-caption-bold text-default-font">
        <QueueSearchText>{sourceValue}</QueueSearchText>
      </span>
    </MetaField>
  );
  const tagContent = shouldRenderStandaloneTagRow ? (
    <TagsManager
      tags={currentTags}
      onTagsChange={onUpdateTags || (() => { })}
      label="Tags"
      inline={true}
      readonly={!onUpdateTags}
      placeholder={onUpdateTags ? "+ Add tags" : (currentTags.length > 0 ? " " : "No tags")}
      className={!onUpdateTags ? "opacity-60" : ""}
    />
  ) : null;
  const descriptionSection = description?.trim() ? (
    <EntityDescription
      description={description}
      className={isDetailVariant ? "-mx-4 -mb-3 border-t border-solid border-neutral-border bg-neutral-500/5 px-4 py-3" : undefined}
      showFullCodeBlocks={isDetailVariant}
    />
  ) : null;

  return (
    <div className={rootClassName}>
      {isDetailVariant && (
        <h2 className="break-words border-b border-solid border-neutral-border pb-3 text-heading-2 font-heading-2 text-default-font">
          <QueueSearchText>{entity.title}</QueueSearchText>
        </h2>
      )}

      <div className={cn("grid min-w-0 gap-3", styles.columns, !isDetailVariant && "border-t border-solid border-neutral-border pt-3")}>
        <div className="flex min-w-0 flex-col">
          {assigneeField}
          <MetaField label="Status" icon={<Activity className="h-3.5 w-3.5" />}>
            <State state={statusValue} className="min-h-6 w-full" />
          </MetaField>

          <MetaField label="Priority" icon={<Flag className="h-3.5 w-3.5" />}>
            {entity.priority ? (
              <Priority priority={priorityToUIPriority(entity.priority)} className="w-full" />
            ) : (
              <span className="text-body font-body text-subtext-color">Not set</span>
            )}
          </MetaField>

          {taskPICERLStage && (
            <MetaField label="PICERL Stage" icon={null}>
              <PicerlStage stage={taskPICERLStage} className="w-full" />
            </MetaField>
          )}
        </div>

        <div className={cn("flex min-w-0 flex-col", styles.recordFields)}>
          {sourceField}
          {taskEntity?.due_date && (
            <TimestampField label={taskDueLabel} value={taskEntity.due_date} icon={<CalendarClock className="h-3.5 w-3.5" />} dueStatus={taskDueStatus} />
          )}

          <TimestampField label="Created" value={entity.created_at} icon={<ClockPlus className="h-3.5 w-3.5" />} />
          <TimestampField label="Updated" value={entity.updated_at} icon={<ClockAlert className="h-3.5 w-3.5" />} />
          {caseEntity?.closed_at && (
            <TimestampField label="Closed" value={caseEntity.closed_at} icon={<ClockAlert className="h-3.5 w-3.5" />} />
          )}

          {creatorField}
        </div>
      </div>

      {isDetailVariant ? (
        <>
          {(tagContent || parentCaseAction) && (
            <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2">
              {tagContent && (
                <div className="flex min-w-0 flex-1 items-center gap-2" aria-label="Tags">
                  <Tags className="h-3.5 w-3.5 flex-none text-subtext-color" aria-hidden="true" />
                  <span className="font-monospace-body text-[10px] uppercase text-subtext-color">Tags</span>
                  {tagContent}
                </div>
              )}
              {parentCaseAction}
            </div>
          )}
          {beforeDescription}
          {descriptionSection}
        </>
      ) : (descriptionSection || tagContent || parentCaseAction) ? (
        <TimelineDescriptionBlock
          variant="timeline"
          className="border-t"
          actionButtons={parentCaseAction}
          tagContent={tagContent}
        >
          {descriptionSection}
        </TimelineDescriptionBlock>
      ) : null}
    </div>
  );
}
