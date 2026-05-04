import React from 'react';
import { useAlertDetail } from '@/hooks/useAlertDetail';
import { AlertCardContent } from '@/components/timeline/AlertCardContent';
import type { AlertRead } from '@/types/generated/models/AlertRead';

interface AlertCardProps {
  /** Alert ID to fetch data for (required for fetching mode) */
  alertId: number;
  /** 
   * Pre-loaded alert data. If provided with sufficient data, no fetch will occur.
   * Use this when you already have the data (e.g., from parent query).
   */
  data?: Partial<AlertRead> & { title: string };
  /** 
   * @deprecated Use `data` prop instead. Fallback data only used when fetch fails.
   */
  fallbackData?: Partial<AlertRead>;
  /** Whether to render the metadata tag section. Timeline embeds render tags in the shared footer. */
  showTags?: boolean;
}

/**
 * AlertCard - Wrapper component that fetches and displays alert metadata
 * 
 * Two usage modes:
 * 1. **Data mode**: Pass `data` prop - renders immediately, no fetch
 * 2. **Fetch mode**: Pass only `alertId` - fetches data then renders
 * 
 * For timeline usage, prefer passing data directly to avoid redundant fetches.
 * For standalone usage (e.g., search results), use alertId-only mode.
 * 
 * @example
 * ```tsx
 * // Data mode - no fetch (preferred in timeline context)
 * <AlertCard alertId={4} data={alertDataFromTimeline} />
 * 
 * // Fetch mode - fetches data by ID
 * <AlertCard alertId={4} />
 * ```
 */
export function AlertCard({ alertId, data, fallbackData, showTags = true }: AlertCardProps) {
  // If data is provided, use it directly without fetching
  const skipFetch = !!data?.title;
  
  const { data: alertDetail, isLoading, error } = useAlertDetail(
    skipFetch ? null : alertId  // Pass null to skip the query
  );

  // Use provided data, fetched data, or fallback
  const displayData = data || alertDetail || fallbackData;

  if (!skipFetch && isLoading) {
    return <AlertCardContent data={{ title: 'Loading...' }} isLoading={true} showTags={showTags} />;
  }

  if (!displayData?.title) {
    return (
      <div className="flex w-full flex-col items-start gap-4 rounded-md border border-solid border-neutral-border px-6 py-6 shadow-md bg-neutral-50">
        <span className="text-body font-body text-subtext-color">
          {error ? 'Error loading alert details' : 'Alert not found'}
        </span>
      </div>
    );
  }

  return <AlertCardContent data={displayData as Partial<AlertRead> & { title: string }} showTags={showTags} />;
}
