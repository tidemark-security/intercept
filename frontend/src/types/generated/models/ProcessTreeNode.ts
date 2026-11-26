/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One process instance observed in a snapshot.
 */
export type ProcessTreeNode = {
    /**
     * Process instance ID unique within the snapshot
     */
    id: string;
    /**
     * Parent instance ID within the snapshot
     */
    parent_id?: (string | null);
    process_name: string;
    /**
     * Operating system process ID
     */
    process_id: number;
    command_line?: (string | null);
    user_account?: (string | null);
    started_at?: (string | null);
    status?: ('running' | 'exited' | null);
};
