import React from 'react';
import { EntityMetadataCard } from '@/components/cards/EntityMetadataCard';
import type { AlertRead } from '@/types/generated/models/AlertRead';

export interface AlertCardContentProps {
  /** Alert data to display - can be full AlertRead or partial data from timeline */
  data: Partial<AlertRead> & { title: string };
  /** Whether data is currently loading (shows skeleton) */
  isLoading?: boolean;
}

/**
 * AlertCardContent - Pure presentation component for alert metadata
 * 
 * Renders alert data using EntityMetadataCard without any data fetching.
 * Use this directly when you already have alert data (e.g., from timeline items).
 * 
 * For standalone usage where data needs to be fetched, use AlertCard instead.
 * 
 * @example
 * ```tsx
 * // Render with data from timeline item
 * <AlertCardContent data={alertDataFromTimeline} />
 * 
 * // Show loading state
 * <AlertCardContent data={partialData} isLoading={true} />
 * ```
 */
export function AlertCardContent({ data, isLoading = false }: AlertCardContentProps) {
  if (isLoading) {
    return (
      <EntityMetadataCard 
        entity={null} 
        entityType="alert" 
        isLoading={true} 
      />
    );
  }

  return (
    <EntityMetadataCard
      entity={data as AlertRead}
      entityType="alert"
      isLoading={false}
    />
  );
}
