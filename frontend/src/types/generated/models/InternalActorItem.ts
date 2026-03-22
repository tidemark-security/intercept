/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TimelineItemAudit } from './TimelineItemAudit';
/**
 * Timeline item for tracking internal actors (employees, contractors).
 */
export type InternalActorItem = {
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
    actor_id?: (number | null);
    snapshot_hash?: (string | null);
    user_id?: (string | null);
    manager_id?: (number | null);
    name?: (string | null);
    title?: (string | null);
    org?: (string | null);
    contact_phone?: (string | null);
    contact_email?: (string | null);
    /**
     * High-profile individual (executive, board member)
     */
    is_vip?: boolean;
    /**
     * User with elevated system privileges
     */
    is_privileged?: boolean;
    /**
     * User poses elevated security risk
     */
    is_high_risk?: boolean;
    /**
     * External contractor or temporary worker
     */
    is_contractor?: boolean;
    /**
     * Non-human service or system account
     */
    is_service_account?: boolean;
};

