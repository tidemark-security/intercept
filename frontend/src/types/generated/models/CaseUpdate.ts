/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AlertItem } from './AlertItem';
import type { AttachmentItem } from './AttachmentItem';
import type { CaseAlertClosureUpdate } from './CaseAlertClosureUpdate';
import type { CaseItem } from './CaseItem';
import type { CaseStatus } from './CaseStatus';
import type { DeletedItem } from './DeletedItem';
import type { EmailItem } from './EmailItem';
import type { ExternalActorItem } from './ExternalActorItem';
import type { ForensicArtifactItem } from './ForensicArtifactItem';
import type { InternalActorItem } from './InternalActorItem';
import type { LinkItem } from './LinkItem';
import type { NetworkTrafficItem } from './NetworkTrafficItem';
import type { NoteItem } from './NoteItem';
import type { ObservableItem } from './ObservableItem';
import type { Priority } from './Priority';
import type { ProcessItem } from './ProcessItem';
import type { RegistryChangeItem } from './RegistryChangeItem';
import type { SystemItem } from './SystemItem';
import type { TaskItem } from './TaskItem';
import type { ThreatActorItem } from './ThreatActorItem';
import type { TTPItem } from './TTPItem';
/**
 * Schema for updating a case.
 */
export type CaseUpdate = {
    title?: (string | null);
    description?: (string | null);
    status?: (CaseStatus | null);
    priority?: (Priority | null);
    assignee?: (string | null);
    tags?: (Array<string> | null);
    timeline_items?: (Record<string, (DeletedItem | InternalActorItem | ExternalActorItem | ThreatActorItem | AlertItem | AttachmentItem | CaseItem | EmailItem | ForensicArtifactItem | LinkItem | NetworkTrafficItem | NoteItem | ObservableItem | ProcessItem | RegistryChangeItem | SystemItem | TaskItem | TTPItem)> | null);
    alert_closure_updates?: (Array<CaseAlertClosureUpdate> | null);
};

