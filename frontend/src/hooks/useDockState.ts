/**
 * Custom hook for managing Right Dock state with localStorage persistence
 * 
 * Features:
 * - Persists dock open/closed state per alert
 * - Persists selected item type per alert
 * - Automatically loads state when alert changes
 * - Assumes closed state for alerts with no saved state
 */

import { useState, useEffect, useCallback } from "react";
import type { TimelineItemType } from "@/types/drafts";
import type { TimelineItem } from "@/types/timeline";
import type { CaseRead } from "@/types/generated/models/CaseRead";
import type { TaskRead } from "@/types/generated/models/TaskRead";
import { saveDockState, loadDockState } from "@/utils/draftStorage";

export interface UseDockStateReturn {
  /** Whether the dock is open */
  isOpen: boolean;
  /** Current item type being edited */
  itemType: TimelineItemType;
  /** Edit mode: if true, form is pre-populated with existing item */
  editMode: boolean;
  /** Item data for edit mode */
  itemData: TimelineItem | CaseRead | TaskRead | undefined;
  /** Files waiting to be consumed by the attachment form (set via paste) */
  pendingFiles: File[];
  /** Open the dock with specified item type for creating a new item */
  openDock: (itemType: TimelineItemType) => void;
  /** Open the dock in edit mode with existing item data */
  openDockForEdit: (itemType: TimelineItemType, itemData: TimelineItem | CaseRead | TaskRead) => void;
  /** Open the attachment dock with pre-staged files (e.g. from clipboard paste) */
  openDockWithFiles: (files: File[]) => void;
  /** Clear pending files after the attachment form has consumed them */
  clearPendingFiles: () => void;
  /** Close the dock */
  closeDock: () => void;
  /** Update item type (without opening/closing) */
  setItemType: (itemType: TimelineItemType) => void;
}

/**
 * Manage Right Dock state with automatic persistence per alert
 * @param alertId Current alert ID (null if no alert selected)
 * @returns Dock state and control functions
 */
export function useDockState(alertId: number | null): UseDockStateReturn {
  const [isOpen, setIsOpen] = useState(false);
  const [itemType, setItemType] = useState<TimelineItemType>("note");
  const [editMode, setEditMode] = useState(false);
  const [itemData, setItemData] = useState<TimelineItem | CaseRead | TaskRead | undefined>(undefined);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);

  // Load dock state when alert changes
  useEffect(() => {
    if (alertId === null) {
      // No alert selected - reset to closed
      setIsOpen(false);
      setItemType("note");
      setEditMode(false);
      setItemData(undefined);
      return;
    }

    // Load persisted state for this alert
    const savedState = loadDockState(alertId);
    
    if (savedState) {
      // Restore saved state (but not edit mode - only create mode persists)
      setIsOpen(savedState.isOpen);
      setItemType(savedState.itemType);
      setEditMode(false);
      setItemData(undefined);
    } else {
      // No saved state - assume closed
      setIsOpen(false);
      setItemType("note");
      setEditMode(false);
      setItemData(undefined);
    }
  }, [alertId]);

  // Save state whenever it changes (with alertId guard)
  // Don't persist edit mode state
  useEffect(() => {
    if (alertId === null) return;

    // Don't persist case_edit or task_edit state as it requires itemData which isn't persisted
    if (itemType === "case_edit" || itemType === "task_edit") return;

    saveDockState(alertId, {
      isOpen,
      itemType,
      lastUpdated: new Date().toISOString(),
    });
  }, [alertId, isOpen, itemType]);

  const openDock = useCallback((newItemType: TimelineItemType) => {
    setItemType(newItemType);
    setEditMode(false);
    setItemData(undefined);
    setIsOpen(true);
  }, []);

  const openDockForEdit = useCallback((newItemType: TimelineItemType, data: TimelineItem | CaseRead | TaskRead) => {
    setItemType(newItemType);
    setEditMode(true);
    setItemData(data);
    setIsOpen(true);
  }, []);

  const openDockWithFiles = useCallback((files: File[]) => {
    setItemType("attachment");
    setEditMode(false);
    setItemData(undefined);
    setPendingFiles(files);
    setIsOpen(true);
  }, []);

  const clearPendingFiles = useCallback(() => {
    setPendingFiles([]);
  }, []);

  const closeDock = useCallback(() => {
    setIsOpen(false);
    // Clear edit mode state when closing
    setEditMode(false);
    setItemData(undefined);
  }, []);

  const updateItemType = useCallback((newItemType: TimelineItemType) => {
    setItemType(newItemType);
  }, []);

  return {
    isOpen,
    itemType,
    editMode,
    itemData,
    pendingFiles,
    openDock,
    openDockForEdit,
    openDockWithFiles,
    clearPendingFiles,
    closeDock,
    setItemType: updateItemType,
  };
}
