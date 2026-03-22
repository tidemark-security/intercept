/**
 * Reply Provider
 * 
 * Provides reply state management for timeline components.
 * Wraps timeline views (alerts, cases) to enable reply functionality.
 */

import React, { useCallback, useState } from "react";
import { ReplyContext, EntityType, ReplyContextState } from "./ReplyContext";

interface ReplyProviderProps {
  children: React.ReactNode;
  entityId: number;
  entityType: EntityType;
}

export function ReplyProvider({ children, entityId, entityType }: ReplyProviderProps) {
  const [activeReplyParentId, setActiveReplyParentId] = useState<string | null>(null);
  const [activeReplyDepth, setActiveReplyDepth] = useState<number>(0);

  const enterReplyMode = useCallback((parentId: string, depth: number) => {
    // Only one reply context can be active at a time
    setActiveReplyParentId(parentId);
    setActiveReplyDepth(depth);
  }, []);

  const exitReplyMode = useCallback(() => {
    setActiveReplyParentId(null);
    setActiveReplyDepth(0);
  }, []);

  const isInReplyMode = useCallback(() => {
    return activeReplyParentId !== null;
  }, [activeReplyParentId]);

  const value: ReplyContextState = {
    activeReplyParentId,
    activeReplyDepth,
    entityId,
    entityType,
    enterReplyMode,
    exitReplyMode,
    isInReplyMode,
  };

  return (
    <ReplyContext.Provider value={value}>
      {children}
    </ReplyContext.Provider>
  );
}
