import React from 'react';
import { EntityMetadataCard, type EntityMetadataCardVariant } from '@/components/cards/EntityMetadataCard';
import type { TaskRead } from '@/types/generated/models/TaskRead';

export interface TaskCardContentProps {
  /** Task data to display - can be full TaskRead or partial data from timeline */
  data: Partial<TaskRead> & { title: string };
  /** Whether data is currently loading (shows skeleton) */
  isLoading?: boolean;
  /** Whether to render the metadata tag section. Timeline embeds render tags in the shared footer. */
  showTags?: boolean;
  /** Presentation density for the shared metadata layout. */
  variant?: EntityMetadataCardVariant;
}

/**
 * TaskCardContent - Pure presentation component for task metadata
 * 
 * Renders task data using EntityMetadataCard without any data fetching.
 * Use this directly when you already have task data (e.g., from timeline items).
 * 
 * For standalone usage where data needs to be fetched, use TaskCard instead.
 * 
 * @example
 * ```tsx
 * // Render with data from timeline item
 * <TaskCardContent data={taskDataFromTimeline} />
 * 
 * // Show loading state
 * <TaskCardContent data={partialData} isLoading={true} />
 * ```
 */
export function TaskCardContent({ data, isLoading = false, showTags = true, variant }: TaskCardContentProps) {
  if (isLoading) {
    return (
      <EntityMetadataCard 
        entity={null} 
        entityType="task" 
        isLoading={true} 
        showTags={showTags}
        variant={variant}
      />
    );
  }

  return (
    <EntityMetadataCard
      entity={data as TaskRead}
      entityType="task"
      isLoading={false}
      showTags={showTags}
      variant={variant}
    />
  );
}
