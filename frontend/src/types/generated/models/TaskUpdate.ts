/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
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
import type { TaskStatus } from './TaskStatus';
import type { ThreatActorItem } from './ThreatActorItem';
import type { TTPItem } from './TTPItem';
/**
 * Schema for updating a task.
 */
export type TaskUpdate = {
    title?: (string | null);
    description?: (string | null);
    status?: (TaskStatus | null);
    priority?: (Priority | null);
    assignee?: (string | null);
    due_date?: (string | null);
    case_id?: (number | null);
    timeline_items?: (Record<string, (DeletedItem | InternalActorItem | ExternalActorItem | ThreatActorItem | AttachmentItem | CaseItem | EmailItem | LinkItem | NetworkTrafficItem | NoteItem | ObservableItem | ProcessItem | RegistryChangeItem | SystemItem | TTPItem)> | null);
    tags?: (Array<string> | null);
};

