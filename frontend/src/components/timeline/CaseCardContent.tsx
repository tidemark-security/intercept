import React from 'react';
import { EntityMetadataCard } from '@/components/cards/EntityMetadataCard';
import type { CaseRead } from '@/types/generated/models/CaseRead';

export interface CaseCardContentProps {
  /** Case data to display - can be full CaseRead or partial data from timeline */
  data: Partial<CaseRead> & { title: string };
  /** Whether data is currently loading (shows skeleton) */
  isLoading?: boolean;
}

/**
 * CaseCardContent - Pure presentation component for case metadata
 * 
 * Renders case data using EntityMetadataCard without any data fetching.
 * Use this directly when you already have case data (e.g., from timeline items).
 * 
 * For standalone usage where data needs to be fetched, use CaseCard instead.
 * 
 * @example
 * ```tsx
 * // Render with data from timeline item
 * <CaseCardContent data={caseDataFromTimeline} />
 * 
 * // Show loading state
 * <CaseCardContent data={partialData} isLoading={true} />
 * ```
 */
export function CaseCardContent({ data, isLoading = false }: CaseCardContentProps) {
  if (isLoading) {
    return (
      <EntityMetadataCard 
        entity={null} 
        entityType="case" 
        isLoading={true} 
      />
    );
  }

  return (
    <EntityMetadataCard
      entity={data as CaseRead}
      entityType="case"
      isLoading={false}
    />
  );
}
