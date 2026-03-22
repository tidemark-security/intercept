import { useSearchParams } from 'react-router-dom';
import { useMemo, useCallback } from 'react';
import { parseRelativeTime, formatForBackend } from '@/utils/dateFilters';
import type { DateRangeValue } from '@/components/forms/DateRangePicker';

export type ReportTabType = 'soc' | 'analyst' | 'alert' | 'ai-triage' | 'ai-chat';

const VALID_TABS: ReportTabType[] = ['soc', 'analyst', 'alert', 'ai-triage', 'ai-chat'];
const DEFAULT_PRESET = '-7d';

/**
 * Hook to sync report state with URL query parameters.
 * 
 * URL format:
 * - /reports?tab=soc&timeframe=-7d (preset timeframe)
 * - /reports?tab=analyst&start=2025-01-01T00:00:00Z&end=2025-01-26T23:59:59Z (custom range)
 * 
 * Features:
 * - Bookmarkable URLs for sharing specific report views
 * - Browser back/forward navigation support
 * - Auto-sync URL on tab/timeframe changes
 */
export function useReportsURLState() {
  const [searchParams, setSearchParams] = useSearchParams();
  
  // Parse tab from URL, default to 'soc'
  const activeTab = useMemo<ReportTabType>(() => {
    const tab = searchParams.get('tab');
    return VALID_TABS.includes(tab as ReportTabType) ? (tab as ReportTabType) : 'soc';
  }, [searchParams]);
  
  // Parse date range from URL
  const dateRange = useMemo<DateRangeValue | null>(() => {
    // Check for preset timeframe (e.g., -7d, -30d)
    const preset = searchParams.get('timeframe');
    if (preset) {
      const range = parseRelativeTime(preset);
      if (range) {
        return {
          start: formatForBackend(range.start),
          end: formatForBackend(range.end),
          preset,
        };
      }
    }
    
    // Check for custom start/end dates
    const start = searchParams.get('start');
    const end = searchParams.get('end');
    if (start && end) {
      return { start, end, preset: 'custom' };
    }
    
    // Check for "all time" indicator
    if (searchParams.get('allTime') === 'true') {
      return null;
    }
    
    // Default to last 7 days if nothing specified
    const defaultRange = parseRelativeTime(DEFAULT_PRESET);
    if (!defaultRange) throw new Error('Invalid default preset');
    return {
      start: formatForBackend(defaultRange.start),
      end: formatForBackend(defaultRange.end),
      preset: DEFAULT_PRESET,
    };
  }, [searchParams]);
  
  // Update tab in URL
  const setActiveTab = useCallback((tab: ReportTabType) => {
    setSearchParams(prev => {
      const params = new URLSearchParams(prev);
      if (tab === 'soc') {
        params.delete('tab'); // Default tab doesn't need to be in URL
      } else {
        params.set('tab', tab);
      }
      return params;
    }, { replace: true });
  }, [setSearchParams]);
  
  // Update date range in URL
  const setDateRange = useCallback((range: DateRangeValue | null) => {
    setSearchParams(prev => {
      const params = new URLSearchParams(prev);
      
      // Clear all date-related params first
      params.delete('timeframe');
      params.delete('start');
      params.delete('end');
      params.delete('allTime');
      
      if (!range) {
        // "All time" selection
        params.set('allTime', 'true');
      } else if (range.preset && range.preset !== 'custom') {
        // Preset timeframe (e.g., -7d, -30d)
        if (range.preset !== DEFAULT_PRESET) {
          params.set('timeframe', range.preset);
        }
        // Default preset doesn't need to be in URL
      } else {
        // Custom date range
        params.set('start', range.start);
        params.set('end', range.end);
      }
      
      return params;
    }, { replace: true });
  }, [setSearchParams]);
  
  return { 
    activeTab, 
    setActiveTab, 
    dateRange, 
    setDateRange 
  };
}
