"use client";

import React from "react";
import { Priority } from "@/components/misc/Priority";
import { State } from "@/components/misc/State";
import { TagsManager } from "@/components/forms/TagsManager";
import { CopyableTimestamp } from "@/components/data-display/CopyableTimestamp";
import { RelativeTime } from "@/components/data-display/RelativeTime";
import MarkdownContent from "@/components/data-display/MarkdownContent";
import { alertStatusToUIState, caseStatusToUIState, taskStatusToUIState, priorityToUIPriority } from "@/utils/statusHelpers";

import type { AlertRead } from "@/types/generated/models/AlertRead";
import type { CaseRead } from "@/types/generated/models/CaseRead";
import type { TaskRead } from "@/types/generated/models/TaskRead";
import type { AlertStatus } from "@/types/generated/models/AlertStatus";
import type { CaseStatus } from "@/types/generated/models/CaseStatus";
import type { TaskStatus } from "@/types/generated/models/TaskStatus";
import { cn } from "@/utils/cn";
import { useTheme } from "@/contexts/ThemeContext";
import { Link } from "@/components/navigation/Link";
import { convertNumericToHumanId } from "@/utils/caseHelpers";

import { User } from 'lucide-react';
interface EntityMetadataCardProps {
  entity: AlertRead | CaseRead | TaskRead | null;
  entityType: "alert" | "case" | "task";
  isLoading?: boolean;
  onUpdateTags?: (tags: string[]) => void;
}

/**
 * EntityMetadataCard - Displays metadata for an Alert or Case
 * 
 * Features:
 * - Shows priority, assignee, dates, description, tags
 * - Adapts to show alert-specific fields (source, case_id) or case-specific fields (created_by, closed_at)
 * - Relative timestamps with ISO8601 format on hover and copy functionality
 * - Markdown support for descriptions
 * - Editable tags using TagsManager component
 * - Loading state support
 * - Responsive two-column layout
 */
export function EntityMetadataCard({ entity, entityType, isLoading, onUpdateTags }: EntityMetadataCardProps) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark";

  // Handle tag operations
  const currentTags = React.useMemo(() => {
    if (!entity) return [];
    const tags = entity.tags;
    if (!tags) return [];
    return Array.isArray(tags) ? tags : [];
  }, [entity]);
  if (isLoading) {
    return (
      <div className="flex w-full flex-col items-start gap-4 rounded-md border border-solid border-neutral-border px-6 py-6 shadow-md">
        <div className="flex h-6 w-full animate-pulse rounded bg-neutral-200" />
        <div className="flex h-px w-full flex-none flex-col items-center gap-2 bg-neutral-border" />
        <div className="flex h-32 w-full animate-pulse rounded bg-neutral-200" />
      </div>
    );
  }

  if (!entity) {
    return (
      <div className="flex w-full flex-col items-start gap-4 rounded-md border border-solid border-neutral-border px-6 py-6 shadow-md">
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

  // Convert API status (UPPERCASE) to UI state (lowercase) for State component
  // Cast to the State component's expected type
  let statusValue: React.ComponentProps<typeof State>['state'];
  if (isAlert) {
    statusValue = alertStatusToUIState(entity.status as AlertStatus) as React.ComponentProps<typeof State>['state'];
  } else if (isTask) {
    statusValue = taskStatusToUIState(entity.status as TaskStatus) as React.ComponentProps<typeof State>['state'];
  } else {
    statusValue = caseStatusToUIState(entity.status as CaseStatus) as React.ComponentProps<typeof State>['state'];
  }

  // Timestamp rendering component
  const TimestampField = ({ label, value, inline = false }: { label: string; value: string; inline?: boolean }) => {

    if (inline) {
      return (
        <div className="flex items-center gap-2 flex-wrap">
          <RelativeTime value={value} className="text-caption font-caption text-default-font" />
        </div>
      );
    }

    return (
      <div className="flex w-full flex-col items-start gap-1">
        <span className="text-caption font-caption text-subtext-color">
          {label}
        </span>
        <div className="flex flex-col items-start gap-1">
          <RelativeTime value={value} className="text-body font-body text-default-font" />
          <CopyableTimestamp value={value} showFull={false} />
        </div>
      </div>
    );
  };

  return (
    <div className="flex w-full flex-col items-start gap-6 rounded-md border border-solid border-neutral-border bg-default-background px-6 py-6">
      {/* State Section */}
      <div className="flex w-full flex-wrap items-start gap-6">
        {/* Status */}
        <div className="flex flex-col items-start gap-1 min-w-[140px]">
          <span className="text-caption font-caption text-subtext-color">
            Status
          </span>
          <State state={statusValue} className="w-full max-w-[200px]" />
        </div>
        
        {/* Priority */}
        <div className="flex flex-col items-start gap-1 min-w-[140px]">
          <span className="text-caption font-caption text-subtext-color">
            Priority
          </span>
          {entity.priority ? (
            <Priority priority={priorityToUIPriority(entity.priority)} className="w-full max-w-[200px]" />
          ) : (
            <span className="text-body font-body text-subtext-color">
              Not set
            </span>
          )}
        </div>

        {/* Assignee */}
        <div className="flex flex-col items-start gap-1 flex-1 max-w-[400px] ml-auto">
          <span className="text-caption font-caption text-subtext-color">
            Assignee
          </span>
          <div className="flex h-6 w-full items-center gap-1 rounded-md border border-solid border-neutral-border bg-neutral-50 px-2">
            <User className="text-body font-body text-neutral-700" />
            <span className="grow shrink-0 basis-0 whitespace-nowrap text-caption font-caption text-neutral-700 text-center overflow-hidden text-ellipsis">
              {entity.assignee || "Unassigned"}
            </span>
          </div>
        </div>
      </div>

      <div className="h-px w-full bg-neutral-border" />

      {/* Metadata Section */}
      <div className="flex w-full flex-wrap items-start gap-6">
        {/* Source/Created By */}
        {(isAlert && alertEntity?.source) || (!isAlert && caseEntity?.created_by) ? (
          <div className="flex flex-col items-start gap-1 min-w-[140px]">
            {isAlert && alertEntity?.source ? (
              <>
                <span className="text-caption font-caption text-subtext-color">
                  Source
                </span>
                <span className="text-body font-body text-default-font">
                  {alertEntity.source}
                </span>
              </>
            ) : (
              <>
                <span className="text-caption font-caption text-subtext-color">
                  Created By
                </span>
                <span className="text-body font-body text-default-font">
                  {caseEntity?.created_by}
                </span>
              </>
            )}
          </div>
        ) : null}

        {/* Created At */}
        <div className="min-w-[140px]">
          <TimestampField 
            label="Created" 
            value={entity.created_at} 
            inline={false}
          />
        </div>
        
        {/* Updated At */}
        <div className="min-w-[140px]">
          <TimestampField 
            label="Updated" 
            value={entity.updated_at} 
            inline={false}
          />
        </div>

        {/* Case ID for alerts/tasks or Closed At for cases */}
        {(isAlert && alertEntity?.case_id) || (isTask && taskEntity?.case_id) || (!isAlert && !isTask && caseEntity?.closed_at) ? (
          <div className="flex flex-col items-start gap-1 min-w-[140px]">
            {isAlert && alertEntity?.case_id ? (
              <>
                <span className="text-caption font-caption text-subtext-color">
                  Case ID
                </span>
                <Link 
                  to={`/cases/${convertNumericToHumanId(alertEntity.case_id)}`}
                  className={cn(
                    "text-body font-body text-default-font hover:underline",
                    isDarkTheme ? "hover:text-brand-primary" : "hover:text-brand-800"
                  )}
                >
                  #{alertEntity.case_id}
                </Link>
              </>
            ) : isTask && taskEntity?.case_id ? (
              <>
                <span className="text-caption font-caption text-subtext-color">
                  Case ID
                </span>
                <Link 
                  to={`/cases/${convertNumericToHumanId(taskEntity.case_id)}`}
                  className={cn(
                    "text-body font-body text-default-font hover:underline",
                    isDarkTheme ? "hover:text-brand-primary" : "hover:text-brand-800"
                  )}
                >
                  #{taskEntity.case_id}
                </Link>
              </>
            ) : !isAlert && !isTask && caseEntity?.closed_at ? (
              <TimestampField 
                label="Closed" 
                value={caseEntity.closed_at} 
                inline={false}
              />
            ) : null}
          </div>
        ) : null}
      </div>

      {/* Description (full width) */}
      {entity.description && (
        <>
          <div className="h-px w-full bg-neutral-border" />
          <div className="flex w-full flex-col items-start gap-1">
            <span className="text-caption font-caption text-subtext-color">
              Description
            </span>
            <div className="w-full">
              <MarkdownContent content={entity.description} />
            </div>
          </div>
        </>
      )}
      
      {/* Tags (full width) */}
      <>
        <div className="h-px w-full bg-neutral-border" />
        <div className="w-full">
          <TagsManager
            tags={currentTags}
            onTagsChange={onUpdateTags || (() => {})}
            label="Tags"
            inline={true}
            readonly={!onUpdateTags}
            placeholder={onUpdateTags ? "+ Add tags" : (currentTags.length > 0 ? " " : "No tags")}
            className={!onUpdateTags ? "pointer-events-none opacity-60" : ""}
          />
        </div>
      </>
    </div>
  );
}
