type EnrichmentTimelineNodeMap = Record<string, EnrichmentTimelineNode>;

interface EnrichmentTimelineNode {
  enrichment_status?: string | null;
  replies?: EnrichmentTimelineNodeMap | null;
}

interface EntityWithTimelineItems {
  timeline_items?: EnrichmentTimelineNodeMap | null;
}

const ACTIVE_ENRICHMENT_STATUSES = new Set(['pending', 'in_progress']);

export function isEnrichmentStatusActive(status: string | null | undefined): boolean {
  const normalizedStatus = status?.trim().toLowerCase();

  return normalizedStatus ? ACTIVE_ENRICHMENT_STATUSES.has(normalizedStatus) : false;
}

function hasActiveTimelineEnrichmentsInItems(items: EnrichmentTimelineNodeMap | null | undefined): boolean {
  if (!items) {
    return false;
  }

  const nodes = Object.values(items);
  if (nodes.length === 0) {
    return false;
  }

  return nodes.some((item) => {
    if (isEnrichmentStatusActive(item.enrichment_status)) {
      return true;
    }

    return hasActiveTimelineEnrichmentsInItems(item.replies);
  });
}

export function hasActiveTimelineEnrichments(entity: EntityWithTimelineItems | null | undefined): boolean {
  return hasActiveTimelineEnrichmentsInItems(entity?.timeline_items);
}