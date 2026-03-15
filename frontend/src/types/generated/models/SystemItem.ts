/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SystemType } from './SystemType';
import type { TimelineItemAudit } from './TimelineItemAudit';
/**
 * Timeline item for affected systems (e.g. servers, workstations).
 */
export type SystemItem = {
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
    hostname?: (string | null);
    ip_address?: (string | null);
    system_type?: (SystemType | null);
    cmdb_id?: (string | null);
    /**
     * Critical business system
     */
    is_critical?: boolean;
    /**
     * System exposed to internet
     */
    is_internet_facing?: boolean;
    /**
     * System poses elevated security risk
     */
    is_high_risk?: boolean;
    /**
     * Legacy/end-of-life system
     */
    is_legacy?: boolean;
    /**
     * System with elevated privileges/access
     */
    is_privileged?: boolean;
};

