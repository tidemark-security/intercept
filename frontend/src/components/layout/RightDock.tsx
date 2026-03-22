/**
 * Right Dock Component
 * 
 * Sliding panel (desktop/tablet) or full-screen modal (mobile) for rich timeline item creation.
 * Features:
 * - Renders existing Dialog components for timeline item forms
 * - Draft auto-save
 * - Responsive: side panel on desktop/tablet, full-screen modal on mobile
 * - Keyboard shortcuts (Escape to close)
 */

import React, { useEffect } from "react";
import type { TimelineItemType } from "@/types/drafts";
import type { TimelineItem } from "@/types/timeline";
import { 
  isNoteItem, isTaskItem, isObservableItem, isSystemItem,
  isInternalActorItem, isExternalActorItem, isThreatActorItem,
  isEmailItem, isLinkItem, isAttachmentItem, isNetworkTrafficItem,
  isProcessItem, isRegistryChangeItem, isTTPItem, isForensicArtifactItem
} from "@/types/timeline";
import { TimelineFormProvider } from "@/contexts/TimelineFormContext";
import { NoteForm } from "@/components/timeline/forms/NoteForm";
import { AddObservableForm } from "@/components/timeline/forms/ObservableForm";
import { AddSystemForm } from "@/components/timeline/forms/SystemForm";
import { AddActorForm } from "@/components/timeline/forms/ActorForm";
import { AddEmailForm } from "@/components/timeline/forms/EmailForm";
import { AddLinkForm } from "@/components/timeline/forms/LinkForm";
import { AddTaskForm } from "@/components/timeline/forms/TaskForm";
import { AddAttachmentForm } from "@/components/timeline/forms/AttachmentForm";
import { AddNetworkForm } from "@/components/timeline/forms/NetworkForm";
import { AddProcessForm } from "@/components/timeline/forms/ProcessForm";
import { AddRegistryForm } from "@/components/timeline/forms/RegistryForm";
import { AddTTPForm } from "@/components/timeline/forms/TTPForm";
import { AddArtifactForm } from "@/components/timeline/forms/ArtifactForm";
import { CaseTaskEditForm } from "@/components/timeline/forms/CaseTaskEditForm";
import type { CaseRead } from "@/types/generated/models/CaseRead";
import type { TaskRead } from "@/types/generated/models/TaskRead";

export interface RightDockProps {
  /** Alert ID for timeline item creation (use when entity type is alert) */
  alertId?: number;
  /** Case ID for timeline item creation (use when entity type is case) */
  caseId?: number;
  /** Task ID for timeline item creation (use when entity type is task) */
  taskId?: number;
  /** Whether dock is open */
  isOpen: boolean;
  /** Type of timeline item being created */
  itemType: TimelineItemType;
  /** Callback when dock should close */
  onClose: () => void;
  /** Callback when timeline item is successfully created, receives the item ID */
  onItemCreated?: (itemId?: string) => void;
  /** Edit mode: if true, pre-populate form with existing item data */
  editMode?: boolean;
  /** Item data to pre-populate when in edit mode */
  itemData?: TimelineItem | CaseRead | TaskRead;
  /** Optional parent item ID for creating replies in a thread */
  parentItemId?: string | null;
  /** Files waiting to be injected into the attachment form (e.g. from clipboard paste) */
  pendingFiles?: File[];
  /** Callback to clear pending files after the attachment form has consumed them */
  onPendingFilesConsumed?: () => void;
}

/**
 * Render form content based on item type.
 * Forms are wrapped with TimelineFormProvider to inject common props via context.
 */
function renderFormContent(
  itemType: TimelineItemType,
  entityId: number,
  onClose: () => void,
  onCreated?: (itemId?: string) => void,
  editMode?: boolean,
  itemData?: TimelineItem | CaseRead | TaskRead,
  parentItemId?: string | null,
  pendingFiles?: File[],
  onPendingFilesConsumed?: () => void,
): React.ReactNode {
  // All forms now only receive initialData prop
  // Common props (alertId, editMode, onCreated, onCancel, parentItemId) come from TimelineFormProvider context
  
  switch (itemType) {
    case "case_edit":
      if (!itemData) return null;
      return <CaseTaskEditForm 
        initialData={itemData as CaseRead}
        type="case"
      />;

    case "task_edit":
      if (!itemData) return null;
      return <CaseTaskEditForm 
        initialData={itemData as TaskRead}
        type="task"
      />;

    case "note":
      return <NoteForm 
        initialData={editMode && itemData && isNoteItem(itemData as TimelineItem) ? (itemData as any) : undefined}
      />;
    
    case "observable":
      return <AddObservableForm 
        initialData={editMode && itemData && isObservableItem(itemData as TimelineItem) ? (itemData as any) : undefined}
      />;
    
    case "system":
      return <AddSystemForm 
        initialData={editMode && itemData && isSystemItem(itemData as TimelineItem) ? (itemData as any) : undefined}
      />;
    
    case "actor": {
      // Actor forms handle all three actor types (internal, external, threat)
      const actorData = editMode && itemData &&
        (isInternalActorItem(itemData as TimelineItem) || isExternalActorItem(itemData as TimelineItem) || isThreatActorItem(itemData as TimelineItem))
        ? (itemData as any)
        : undefined;
      return <AddActorForm initialData={actorData} />;
    }
    
    case "email":
      return <AddEmailForm 
        initialData={editMode && itemData && isEmailItem(itemData as TimelineItem) ? (itemData as any) : undefined}
      />;
    
    case "link":
      return <AddLinkForm 
        initialData={editMode && itemData && isLinkItem(itemData as TimelineItem) ? (itemData as any) : undefined}
      />;
    
    case "task":
      return <AddTaskForm 
        initialData={editMode && itemData && isTaskItem(itemData as TimelineItem) ? (itemData as any) : undefined}
      />;
    
    case "attachment":
      return <AddAttachmentForm 
        initialData={editMode && itemData && isAttachmentItem(itemData as TimelineItem) ? (itemData as any) : undefined}
        pendingFiles={pendingFiles}
        onPendingFilesConsumed={onPendingFilesConsumed}
      />;
    
    case "network_traffic":
      return <AddNetworkForm 
        initialData={editMode && itemData && isNetworkTrafficItem(itemData as TimelineItem) ? (itemData as any) : undefined}
      />;
    
    case "registry_change":
      return <AddRegistryForm 
        initialData={editMode && itemData && isRegistryChangeItem(itemData as TimelineItem) ? (itemData as any) : undefined}
      />;
    
    case "ttp":
      return <AddTTPForm 
        initialData={editMode && itemData && isTTPItem(itemData as TimelineItem) ? (itemData as any) : undefined}
      />;
    
    case "forensic_artifact":
      return <AddArtifactForm 
        initialData={editMode && itemData && isForensicArtifactItem(itemData as TimelineItem) ? (itemData as any) : undefined}
      />;
    
    case "process":
      return <AddProcessForm 
        initialData={editMode && itemData && isProcessItem(itemData as TimelineItem) ? (itemData as any) : undefined}
      />;
    
    default:
      return null;
  }
}

export function RightDock({
  alertId,
  caseId,
  taskId,
  isOpen,
  itemType,
  onClose,
  onItemCreated,
  editMode = false,
  itemData,
  parentItemId,
  pendingFiles,
  onPendingFilesConsumed,
}: RightDockProps) {
  // Determine which entity ID to use
  const entityId = alertId || caseId || taskId;

  // Handle Escape key to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!entityId) {
    console.error("RightDock requires either alertId, caseId, or taskId");
    return null;
  }

  if (!isOpen) return null;

  return (
    <div className="flex h-full flex-col items-start self-stretch w-full max-w-[576px]">
      {/* Content */}
      <div className="flex-1 w-full overflow-auto">
        {/* Wrap form with TimelineFormProvider to inject common props via context */}
        <TimelineFormProvider
          alertId={alertId}
          caseId={caseId}
          taskId={taskId}
          itemType={itemType}
          editMode={editMode}
          parentItemId={parentItemId || null}
          onSuccess={onItemCreated || (() => {})}
          onCancel={onClose}
        >
          {renderFormContent(itemType, entityId, onClose, onItemCreated, editMode, itemData, parentItemId, pendingFiles, onPendingFilesConsumed)}
        </TimelineFormProvider>
      </div>
    </div>
  );
}
