/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PinnedAlertFilterBadge } from './PinnedAlertFilterBadge';
import type { SidebarBadgeCount } from './SidebarBadgeCount';
/**
 * Response model for sidebar badge counts.
 */
export type SidebarBadgeCountsResponse = {
    alerts: SidebarBadgeCount;
    cases: SidebarBadgeCount;
    tasks: SidebarBadgeCount;
    pinned_alert_filters: Array<PinnedAlertFilterBadge>;
};

