/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TimelineItemAudit } from './TimelineItemAudit';
/**
 * An observed action attributed to an AI agent or its harness.
 */
export type AIAgentItem = {
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
    replies?: (Record<string, Record<string, any>> | null);
    /**
     * Response-only audit metadata dynamically coalesced from audit logs
     */
    audit?: (TimelineItemAudit | null);
    activity: 'tool_call' | 'file_read' | 'file_write' | 'shell_command' | 'other';
    /**
     * Observed harness identifier, e.g. codex_cli or claude_code. Custom identifiers are accepted.
     */
    harness?: (string | null);
    /**
     * Name of the agent within the harness
     */
    agent_name?: (string | null);
    /**
     * Observed tool, including tools that read or write files or run commands
     */
    tool_name?: (string | null);
    file_path?: (string | null);
    command_line?: (string | null);
    /**
     * Endpoint on which the action was observed
     */
    endpoint?: (string | null);
    /**
     * Event identifier in the source telemetry
     */
    source_event_id?: (string | null);
    outcome?: ('succeeded' | 'failed' | 'blocked' | null);
    exit_code?: (number | null);
};
