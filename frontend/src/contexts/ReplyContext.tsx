/**
 * Reply Context
 * 
 * Provides state management for timeline item reply mode.
 * Manages which timeline item is being replied to and provides
 * enter/exit functionality for reply mode.
 */

/* eslint-disable react-refresh/only-export-components */

import { createContext, useContext } from 'react';

export type EntityType = 'alert' | 'case' | 'task';

export interface ReplyContextState {
  /** ID of timeline item being replied to (null when not in reply mode) */
  activeReplyParentId: string | null;
  
  /** Nesting depth of current reply (0 for top-level reply) */
  activeReplyDepth: number;
  
  /** Entity context (alert or case) for reply submission */
  entityId: number;
  entityType: EntityType;
  
  /** Enter reply mode for a specific parent item */
  enterReplyMode: (parentId: string, depth: number) => void;
  
  /** Exit reply mode and return to normal state */
  exitReplyMode: () => void;
  
  /** Check if currently in reply mode */
  isInReplyMode: () => boolean;
}

export const ReplyContext = createContext<ReplyContextState | undefined>(undefined);

export function useReplyMode() {
  const context = useContext(ReplyContext);
  if (!context) {
    throw new Error('useReplyMode must be used within a ReplyProvider');
  }
  return context;
}
