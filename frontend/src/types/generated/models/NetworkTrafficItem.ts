/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Protocol } from './Protocol';
import type { TimelineItemAudit } from './TimelineItemAudit';
/**
 * Timeline item for network traffic events.
 */
export type NetworkTrafficItem = {
    /**
     * Unique identifier for timeline item
     */
    id?: string;
    type?: string;
    /**
     * Free text description of the timeline item
     */
    description?: (string | null);
    /**
     * Timestamp when item was created
     */
    created_at?: string;
    /**
     * Timestamp when event occurred
     */
    timestamp?: string;
    /**
     * User who created this timeline item
     */
    created_by?: string;
    tags?: (Array<string> | null);
    /**
     * Whether this item is flagged as significant
     */
    flagged?: boolean;
    /**
     * Whether this item is highlighted for attention
     */
    highlighted?: boolean;
    /**
     * Background enrichment status
     */
    enrichment_status?: (string | null);
    /**
     * Linked pgqueuer job id for the active enrichment task
     */
    enrichment_task_id?: (string | null);
    /**
     * Provider enrichment payloads keyed by provider identifier
     */
    enrichments?: (Record<string, any> | null);
    /**
     * ID of parent timeline item for replies (null for top-level items)
     */
    parent_id?: (string | null);
    /**
     * Optional nested timeline items as replies (typed in Union definitions)
     */
    replies?: null;
    /**
     * Response-only audit metadata dynamically coalesced from audit logs
     */
    audit?: (TimelineItemAudit | null);
    source_ip?: (string | null);
    destination_ip?: (string | null);
    source_port?: (number | null);
    destination_port?: (number | null);
    protocol?: (Protocol | null);
    bytes_sent?: (number | null);
    bytes_received?: (number | null);
    duration?: (number | null);
};

