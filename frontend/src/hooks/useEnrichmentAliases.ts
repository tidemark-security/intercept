import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { EnrichmentsService } from '@/types/generated/services/EnrichmentsService';
import type { EnrichmentAliasRead } from '@/types/generated/models/EnrichmentAliasRead';

const ENRICHMENT_ALIASES_QUERY_KEY = ['enrichments', 'aliases'] as const;

interface UseEnrichmentAliasesOptions {
  query: string;
  entityType: string;
  providerId?: string;
  limit?: number;
  enabled?: boolean;
}

export function useEnrichmentAliases({
  query,
  entityType,
  providerId,
  limit = 8,
  enabled = true,
}: UseEnrichmentAliasesOptions): UseQueryResult<EnrichmentAliasRead[], Error> {
  const normalizedQuery = query.trim();

  return useQuery({
    queryKey: [
      ...ENRICHMENT_ALIASES_QUERY_KEY,
      { query: normalizedQuery, entityType, providerId: providerId ?? null, limit },
    ],
    queryFn: () =>
      EnrichmentsService.searchAliasesApiV1EnrichmentsAliasesSearchGet({
        q: normalizedQuery,
        entityType,
        providerId,
        limit,
      }),
    enabled: enabled && normalizedQuery.length > 0,
    staleTime: 60_000,
  });
}
