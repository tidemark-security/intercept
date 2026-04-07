/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AlertStatus } from './AlertStatus';
import type { AttachmentItem } from './AttachmentItem';
import type { CaseItem } from './CaseItem';
import type { DeletedItem } from './DeletedItem';
import type { EmailItem } from './EmailItem';
import type { ExternalActorItem } from './ExternalActorItem';
import type { InternalActorItem } from './InternalActorItem';
import type { LinkItem } from './LinkItem';
import type { NetworkTrafficItem } from './NetworkTrafficItem';
import type { NoteItem } from './NoteItem';
import type { ObservableItem } from './ObservableItem';
import type { Priority } from './Priority';
import type { ProcessItem } from './ProcessItem';
import type { RegistryChangeItem } from './RegistryChangeItem';
import type { SystemItem } from './SystemItem';
import type { ThreatActorItem } from './ThreatActorItem';
import type { TriageRecommendationRead } from './TriageRecommendationRead';
import type { TTPItem } from './TTPItem';
/**
 * Schema for reading an alert.
 */
export type AlertRead = {
    title: string;
    description?: (string | null);
    priority?: (Priority | null);
    source?: (string | null);
    id: number;
    status: AlertStatus;
    assignee?: (string | null);
    triaged_at?: (string | null);
    triage_notes?: (string | null);
    case_id?: (number | null);
    linked_at?: (string | null);
    created_at: string;
    updated_at: string;
    timeline_items?: (Record<string, (DeletedItem | InternalActorItem | ExternalActorItem | ThreatActorItem | AttachmentItem | CaseItem | EmailItem | LinkItem | NetworkTrafficItem | NoteItem | ObservableItem | ProcessItem | RegistryChangeItem | SystemItem | TTPItem)> | null);
    tags?: (Array<string> | null);
    triage_recommendation?: (TriageRecommendationRead | null);
    readonly human_id: string;
};

