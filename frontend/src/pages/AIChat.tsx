/**
 * AIChat Page
 * 
 * Standalone AI chat page for security analysts with chat history sidebar.
 * Uses ThreeColumnLayout with:
 * - Left: Chat history list (collapsible)
 * - Center: Active AI chat conversation
 * - Right: Unused (reserved for future features)
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { DefaultPageLayout } from '@/components/layout/DefaultPageLayout';
import { ThreeColumnLayout } from '../components/layout/ThreeColumnLayout';
import { getPersistedWidth } from '../components/layout/ColumnRail';
import { AiChat } from '../components/ai';
import { ChatHistoryList } from '@/components/ai/ChatHistoryList';
import { useBreakpointContext } from '../contexts/BreakpointContext';
import { useSession } from '../contexts/sessionContext';
import type { VisibleColumns } from '../components/layout/ThreeColumnLayout.types';
import type { LangFlowSession } from '../services/langflowApi';

// LocalStorage keys for persistence
const HISTORY_COLLAPSED_KEY = 'ai-chat-history-collapsed';
const HISTORY_WIDTH_KEY = 'ai-chat-history-width';

/**
 * Get persisted collapsed state from localStorage
 */
function getPersistedCollapsed(): boolean {
  if (typeof window === 'undefined') return false;
  const stored = localStorage.getItem(HISTORY_COLLAPSED_KEY);
  return stored === 'true';
}

/**
 * Get persisted width from localStorage
 */
function getPersistedHistoryWidth(): number {
  if (typeof window === 'undefined') return 320;
  const stored = localStorage.getItem(HISTORY_WIDTH_KEY);
  const parsed = stored ? parseInt(stored, 10) : 320;
  return isNaN(parsed) ? 320 : parsed;
}

/**
 * Column config for AIChat page layout
 */
const aiChatColumnConfig = {
  ultrawide: {
    leftWidth: 'w-[320px]',
    centerWidth: 'grow',
  },
  desktop: {
    leftWidth: 'w-[320px]',
    centerWidth: 'grow',
  },
  tablet: {
    leftWidth: 'w-[280px]',
    centerWidth: 'grow',
  },
  mobile: {
    leftWidth: 'w-full',
    centerWidth: 'w-full',
  },
};

export function AIChat() {
  const { breakpoint } = useBreakpointContext();
  const { user } = useSession();
  const currentUser = user?.username || null;
  
  // History pane visibility (persisted on desktop, always start collapsed on mobile)
  const [historyCollapsed, setHistoryCollapsed] = useState<boolean>(() => {
    // On mobile, always start with history collapsed to show chat first
    if (typeof window !== 'undefined' && window.innerWidth < 768) {
      return true;
    }
    return getPersistedCollapsed();
  });
  const [historyWidth, setHistoryWidth] = useState<number>(() => getPersistedHistoryWidth());
  
  // Column visibility state
  const [visibleColumns, setVisibleColumns] = useState<VisibleColumns>(() => {
    // On mobile, start with center (chat) visible
    if (typeof window !== 'undefined' && window.innerWidth < 768) {
      return 'center';
    }
    // Otherwise show history + chat
    return getPersistedCollapsed() ? 'center' : 'left+center';
  });
  
  // Session selection state
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  
  // Key to force AiChat remount when session changes
  const [chatKey, setChatKey] = useState(0);
  
  // Key to trigger refresh of ChatHistoryList
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);
  
  // Track if we've done initial auto-select
  const hasAutoSelectedRef = useRef(false);

  // Toggle history pane visibility
  const handleToggleHistory = useCallback(() => {
    setHistoryCollapsed(prev => {
      const newValue = !prev;
      localStorage.setItem(HISTORY_COLLAPSED_KEY, String(newValue));
      return newValue;
    });
  }, []);

  // Handle history width changes
  const handleHistoryWidthChange = useCallback((width: number) => {
    setHistoryWidth(width);
    localStorage.setItem(HISTORY_WIDTH_KEY, String(width));
  }, []);

  // Adjust visible columns based on breakpoint and collapsed state
  useEffect(() => {
    if (breakpoint === 'mobile') {
      // Mobile: show single column at a time based on collapsed state
      // When history is open (not collapsed) → show history (left)
      // When history is closed (collapsed) → show chat (center)
      setVisibleColumns(historyCollapsed ? 'center' : 'left');
    } else {
      // Desktop/Tablet/Ultrawide: respect collapsed state
      setVisibleColumns(historyCollapsed ? 'center' : 'left+center');
    }
  }, [breakpoint, historyCollapsed]);

  // Handle session selection from history
  const handleSelectSession = useCallback((sessionId: string | null) => {
    setSelectedSessionId(sessionId);
    // Increment key to force remount of AiChat with new session
    setChatKey(prev => prev + 1);
    
    // On mobile, collapse history to show chat when session is selected
    if (breakpoint === 'mobile' && sessionId) {
      setHistoryCollapsed(true);
      localStorage.setItem(HISTORY_COLLAPSED_KEY, 'true');
    }
  }, [breakpoint]);

  // Handle "New Chat" button
  const handleNewChat = useCallback(() => {
    setSelectedSessionId(null);
    // Increment key to force remount of AiChat for new session
    setChatKey(prev => prev + 1);
    
    // On mobile, collapse history to show chat
    if (breakpoint === 'mobile') {
      setHistoryCollapsed(true);
      localStorage.setItem(HISTORY_COLLAPSED_KEY, 'true');
    }
  }, [breakpoint]);

  // Handle session change from AiChat (when new session is created)
  const handleSessionChange = useCallback((sessionId: string | null) => {
    if (sessionId && sessionId !== selectedSessionId) {
      setSelectedSessionId(sessionId);
      // Trigger refresh of history list to show the new session
      setHistoryRefreshKey(prev => prev + 1);
    }
  }, [selectedSessionId]);

  // Handle when sessions are loaded from ChatHistoryList
  // Auto-select the most recent session on first load
  const handleSessionsLoaded = useCallback((sessions: LangFlowSession[]) => {
    // Only auto-select on initial load, not on subsequent refreshes
    if (hasAutoSelectedRef.current) return;
    hasAutoSelectedRef.current = true;
    
    // If there are existing sessions, select the most recent one
    if (sessions.length > 0) {
      const mostRecent = sessions[0]; // Sessions are sorted by updated_at desc
      setSelectedSessionId(mostRecent.id);
      setChatKey(prev => prev + 1);
    }
    // If no sessions exist, AiChat will create a new one on mount
  }, []);

  return (
    <DefaultPageLayout>
      <ThreeColumnLayout
        visibleColumns={visibleColumns}
        onVisibleColumnsChange={setVisibleColumns}
        columnConfig={aiChatColumnConfig}
        showLeftRail={breakpoint !== 'mobile'}
        leftRailCollapsed={historyCollapsed}
        onLeftRailToggle={handleToggleHistory}
        leftColumnWidth={historyWidth}
        onLeftColumnWidthChange={handleHistoryWidthChange}
        leftColumn={
          <ChatHistoryList
            selectedSessionId={selectedSessionId}
            onSelectSession={handleSelectSession}
            onNewChat={handleNewChat}
            onClose={handleToggleHistory}
            onSessionsLoaded={handleSessionsLoaded}
            refreshKey={historyRefreshKey}
          />
        }
        centerColumn={
          <AiChat
            key={chatKey}
            contextType="general"
            username={currentUser ?? undefined}
            inputPlaceholder="Ask about threat analysis, incident response, or investigation techniques..."
            initialSessionId={selectedSessionId ?? undefined}
            onSessionChange={handleSessionChange}
            persistSession={false}
            showHistoryButton={historyCollapsed}
            onHistoryClick={handleToggleHistory}
          />
        }
      />
    </DefaultPageLayout>
  );
}
