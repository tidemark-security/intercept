interface EnrichmentTimelineNode {
  enrichment_status?: string | null;
  replies?: EnrichmentTimelineNode[] | null;
}

interface EntityWithTimelineItems {
  timeline_items?: EnrichmentTimelineNode[] | null;
}

const ACTIVE_ENRICHMENT_STATUSES = new Set(['pending', 'in_progress']);

export function isEnrichmentStatusActive(status: string | null | undefined): boolean {
  const normalizedStatus = status?.trim().toLowerCase();

  return normalizedStatus ? ACTIVE_ENRICHMENT_STATUSES.has(normalizedStatus) : false;
}

function hasActiveTimelineEnrichmentsInItems(items: EnrichmentTimelineNode[] | null | undefined): boolean {
  if (!Array.isArray(items) || items.length === 0) {
    return false;
  }

  return items.some((item) => {
    if (isEnrichmentStatusActive(item.enrichment_status)) {
      return true;
    }

    return hasActiveTimelineEnrichmentsInItems(item.replies);
  });
}

export function hasActiveTimelineEnrichments(entity: EntityWithTimelineItems | null | undefined): boolean {
  return hasActiveTimelineEnrichmentsInItems(entity?.timeline_items);
}