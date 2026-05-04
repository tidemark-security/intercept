/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TimelineGraphOperation = {
    type: 'add_node' | 'add_group' | 'move_node' | 'resize_node' | 'update_node_metadata' | 'remove_node' | 'add_edge' | 'reconnect_edge' | 'remove_edge' | 'update_edge_label' | 'update_edge_metadata';
    node_id?: (string | null);
    edge_id?: (string | null);
    item_id?: (string | null);
    position?: (Record<string, number> | null);
    width?: (number | null);
    height?: (number | null);
    parent_node_id?: (string | null);
    source?: (string | null);
    target?: (string | null);
    source_handle?: (string | null);
    target_handle?: (string | null);
    label?: (string | null);
    marker?: ('none' | 'forward' | 'reverse' | 'bidirectional' | null);
};

