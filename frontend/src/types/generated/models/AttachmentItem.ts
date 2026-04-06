/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TimelineItemAudit } from './TimelineItemAudit';
import type { UploadStatus } from './UploadStatus';
/**
 * Timeline item for file attachments.
 */
export type AttachmentItem = {
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
    file_name?: (string | null);
    mime_type?: (string | null);
    file_size?: (number | null);
    /**
     * Object storage key (e.g., alerts/123/attachments/abc/uuid.pdf)
     */
    storage_key?: (string | null);
    /**
     * SHA256 hash of file content for integrity verification
     */
    file_hash?: (string | null);
    /**
     * Username of user who uploaded the file
     */
    uploaded_by?: (string | null);
    /**
     * Current upload state
     */
    upload_status?: UploadStatus;
    url?: (string | null);
};

