import { useQuery, UseQueryResult } from '@tanstack/react-query';
import { FeaturesService } from '@/types/generated/services/FeaturesService';
import type { FeatureFlags } from '@/types/generated/models/FeatureFlags';

/**
 * Hook to fetch public feature flags from the backend.
 * 
 * Feature flags include:
 * - ai_triage_enabled: Whether AI triage is available (LangFlow alert triage flow is configured)
 * - ai_triage_auto_enqueue: Whether to automatically enqueue triage when alerts are created
 * 
 * Flags are cached aggressively (5 min stale time) since they rarely change.
 * 
 * @returns Query result with feature flags
 */
export function useFeatureFlags(): UseQueryResult<FeatureFlags, Error> {
  return useQuery<FeatureFlags, Error>({
    queryKey: ['features'],
    queryFn: () => FeaturesService.getFeatureFlagsApiV1FeaturesGet(),
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes (formerly cacheTime)
    refetchOnWindowFocus: false, // Don't refetch on focus - flags rarely change
  });
}
