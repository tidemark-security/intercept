/**
 * ChatHistoryList - Display and manage chat session history
 * 
 * Features:
 * - List all user's chat sessions in reverse chronological order
 * - "New Chat" button to start fresh conversation
 * - Session selection with highlighting
 * - Inline rename (edit icon)
 * - Delete with confirmation
 * - Message count and timestamp display
 */

import React, { useState, useEffect, useCallback, useRef, useReducer } from 'react';
import { IconButton } from '@/components/buttons/IconButton';
import { Button } from '@/components/buttons/Button';
import { Dialog } from '@/components/overlays/Dialog';
import { useTheme } from '@/contexts/ThemeContext';
import { RelativeTime } from '@/components/data-display/RelativeTime';

import * as langflowApi from '@/services/langflowApi';
import type { LangFlowSession } from '@/services/langflowApi';
import { getTimeGroup, TIME_GROUP_LABELS, type TimeGroup } from '@/utils/dateFormatters';
import { IconWithBackground } from '@/components/misc/IconWithBackground';

import { AlertCircle, Check, Edit2, History, Loader, MessageSquare, Plus, Trash2, X } from 'lucide-react';
// ============================================================================
// Types
// ============================================================================

export interface ChatHistoryListProps {
    /** Currently selected session ID */
    selectedSessionId: string | null;
    /** Callback when a session is selected */
    onSelectSession: (sessionId: string | null) => void;
    /** Callback when "New Chat" is clicked */
    onNewChat: () => void;
    /** Callback when the close button is clicked */
    onClose?: () => void;
    /** Callback when sessions are loaded (provides the sessions list) */
    onSessionsLoaded?: (sessions: LangFlowSession[]) => void;
    /** Key to trigger refresh of sessions list */
    refreshKey?: number;
    /** Additional class names */
    className?: string;
}

/** Session interaction state for edit/delete modes */
type SessionInteractionState = 
    | { mode: 'idle' }
    | { mode: 'editing'; sessionId: string; title: string }
    | { mode: 'deleting'; sessionId: string };

type SessionInteractionAction =
    | { type: 'start-edit'; sessionId: string; title: string }
    | { type: 'update-title'; title: string }
    | { type: 'start-delete'; sessionId: string }
    | { type: 'reset' };

// ============================================================================
// Helpers
// ============================================================================

function sessionInteractionReducer(
    state: SessionInteractionState,
    action: SessionInteractionAction
): SessionInteractionState {
    switch (action.type) {
        case 'start-edit':
            return { mode: 'editing', sessionId: action.sessionId, title: action.title };
        case 'update-title':
            if (state.mode !== 'editing') return state;
            return { ...state, title: action.title };
        case 'start-delete':
            return { mode: 'deleting', sessionId: action.sessionId };
        case 'reset':
            return { mode: 'idle' };
        default:
            return state;
    }
}

/**
 * Group sessions by time period
 */
function groupSessionsByTime(sessions: LangFlowSession[]): Map<string, LangFlowSession[]> {
    const groups = new Map<string, LangFlowSession[]>();
    const groupOrder: TimeGroup[] = ['today', 'yesterday', 'week', 'older'];

    // Initialize groups in order
    groupOrder.forEach(key => groups.set(TIME_GROUP_LABELS[key], []));

    // Distribute sessions into groups
    sessions.forEach(session => {
        const group = getTimeGroup(session.updated_at);
        const label = TIME_GROUP_LABELS[group];
        groups.get(label)?.push(session);
    });

    // Remove empty groups
    groups.forEach((sessions, key) => {
        if (sessions.length === 0) groups.delete(key);
    });

    return groups;
}

/**
 * Generate a display title for a session
 */
function getSessionTitle(session: LangFlowSession): string {
    // Prefer the dedicated title field
    if (session.title) {
        return session.title;
    }
    
    // Fall back to context.title for legacy sessions
    if (session.context?.title) {
        return session.context.title;
    }

    // Default to a formatted date/time
    const date = new Date(session.created_at);
    return `Chat ${date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
    })}`;
}

// ============================================================================
// Subcomponents
// ============================================================================

interface ClearAllDialogProps {
    open: boolean;
    onClose: () => void;
    onConfirm: () => Promise<void>;
    sessionCount: number;
    loading: boolean;
}

function ClearAllDialog({ open, onClose, onConfirm, sessionCount, loading }: ClearAllDialogProps) {
    return (
        <Dialog open={open} onOpenChange={onClose}>
            <Dialog.Content className="p-6 max-w-sm">
                <div className="flex flex-col gap-4">
                    <IconWithBackground icon={<Trash2 />} variant="error" size="medium"/>
                    <div className="flex items-center gap-3">
                        
                        <div className="flex flex-col gap-1">
                            <span className="text-heading-3 font-heading-3 text-default-font">
                                Clear All Chats
                            </span>
                            <span className="text-body font-body text-subtext-color">
                                Are you sure you want to delete all {sessionCount} chat{sessionCount !== 1 ? 's' : ''}? This action cannot be undone.
                            </span>
                        </div>
                    </div>
                    <div className="flex items-center justify-end gap-2">
                        <Button
                            variant="neutral-secondary"
                            size="small"
                            onClick={onClose}
                            disabled={loading}
                        >
                            Cancel
                        </Button>
                        <Button
                            variant="destructive-primary"
                            size="small"
                            icon={loading ? <Loader className="animate-spin" /> : <Trash2 />}
                            onClick={onConfirm}
                            disabled={loading}
                        >
                            {loading ? 'Clearing...' : 'Clear All'}
                        </Button>
                    </div>
                </div>
            </Dialog.Content>
        </Dialog>
    );
}

interface SessionItemProps {
    session: LangFlowSession;
    isSelected: boolean;
    isDarkTheme: boolean;
    isEditing: boolean;
    isDeleting: boolean;
    editTitle: string;
    editInputRef: React.RefObject<HTMLInputElement>;
    onEditTitleChange: (title: string) => void;
    onStartEdit: (e: React.MouseEvent) => void;
    onSaveEdit: (e: React.MouseEvent) => void;
    onCancelEdit: (e: React.MouseEvent) => void;
    onEditKeyDown: (e: React.KeyboardEvent) => void;
    onStartDelete: (e: React.MouseEvent) => void;
    onConfirmDelete: (e: React.MouseEvent) => void;
    onCancelDelete: (e: React.MouseEvent) => void;
    onClick: () => void;
}

function SessionItem({
    session,
    isSelected,
    isDarkTheme,
    isEditing,
    isDeleting,
    editTitle,
    editInputRef,
    onEditTitleChange,
    onStartEdit,
    onSaveEdit,
    onCancelEdit,
    onEditKeyDown,
    onStartDelete,
    onConfirmDelete,
    onCancelDelete,
    onClick,
}: SessionItemProps) {
    return (
        <div
            className={`
                group flex w-full items-start gap-3 rounded-sm border border-solid px-4 py-3 cursor-pointer transition-colors
                ${isSelected 
                    ? 'border-accent-1-primary bg-neutral-0' 
                    : 'border-neutral-border bg-neutral-0 hover:`border-brand-primary`'}
            `}
            onClick={onClick}
        >
            {/* Content */}
            <div className="flex grow shrink-0 basis-0 flex-col items-start gap-1 min-w-0">
                {isEditing ? (
                    <div className="flex w-full items-center gap-1">
                        <input
                            ref={editInputRef}
                            type="text"
                            value={editTitle}
                            onChange={(e) => onEditTitleChange(e.target.value)}
                            onKeyDown={onEditKeyDown}
                            onClick={(e) => e.stopPropagation()}
                            className="flex-1 min-w-0 px-2 py-1 text-body font-body text-default-font bg-white border border-neutral-border rounded focus:outline-none focus:border-brand-primary"
                        />
                        <IconButton
                            size="small"
                            icon={<Check />}
                            onClick={onSaveEdit}
                        />
                        <IconButton
                            size="small"
                            icon={<X />}
                            onClick={onCancelEdit}
                        />
                    </div>
                ) : isDeleting ? (
                    <div className="flex items-center gap-2">
                        <span className="text-body-small font-body text-error-600">Delete this chat?</span>
                        <IconButton
                            size="small"
                            icon={<Check />}
                            onClick={onConfirmDelete}
                        />
                        <IconButton
                            size="small"
                            icon={<X />}
                            onClick={onCancelDelete}
                        />
                    </div>
                ) : (
                    <>
                        <span className={`w-full text-body-bold font-body-bold truncate ${isSelected ? (isDarkTheme ? 'text-accent-1-400' : 'text-accent-1-900') : (isDarkTheme ? 'text-[#fafafaff] group-hover:text-brand-400' : 'text-default-font group-hover:text-default-font')}`}>
                            {getSessionTitle(session)}
                        </span>
                        <span className="text-caption font-caption text-subtext-color">
                            {session.message_count !== undefined && session.message_count > 0 
                                ? (
                                    <>
                                        {session.message_count} message{session.message_count !== 1 ? 's' : ''} • <RelativeTime value={session.updated_at} />
                                    </>
                                )
                                : <RelativeTime value={session.updated_at} />
                            }
                        </span>
                    </>
                )}
            </div>

            {/* Actions - visible on hover */}
            {!isEditing && !isDeleting && (
                <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                    <IconButton
                        variant="neutral-tertiary"
                        size="small"
                        icon={<Edit2 />}
                        onClick={onStartEdit}
                    />
                    <IconButton
                        variant="neutral-tertiary"
                        size="small"
                        icon={<Trash2 />}
                        onClick={onStartDelete}
                    />
                </div>
            )}
        </div>
    );
}

export function ChatHistoryList({
    selectedSessionId,
    onSelectSession,
    onNewChat,
    onClose,
    onSessionsLoaded,
    refreshKey,
    className = '',
}: ChatHistoryListProps) {
    const { resolvedTheme } = useTheme();
    const isDarkTheme = resolvedTheme === 'dark';

    const [sessions, setSessions] = useState<LangFlowSession[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Session interaction state (edit/delete modes)
    const [interaction, dispatch] = useReducer(sessionInteractionReducer, { mode: 'idle' });
    const editInputRef = useRef<HTMLInputElement>(null);
    
    // Clear all modal state
    const [showClearAllModal, setShowClearAllModal] = useState(false);
    const [clearAllLoading, setClearAllLoading] = useState(false);

    // Derived state
    const editingSessionId = interaction.mode === 'editing' ? interaction.sessionId : null;
    const editTitle = interaction.mode === 'editing' ? interaction.title : '';
    const deletingSessionId = interaction.mode === 'deleting' ? interaction.sessionId : null;

    /**
     * Load sessions from API
     */
    const loadSessions = useCallback(async () => {
        setIsLoading(true);
        setError(null);

        try {
            const data = await langflowApi.listSessions();
            setSessions(data);
            if (onSessionsLoaded) {
                onSessionsLoaded(data);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load chat history');
        } finally {
            setIsLoading(false);
        }
    }, [onSessionsLoaded]);

    // Load sessions on mount and when refreshKey changes
    useEffect(() => {
        loadSessions();
    }, [loadSessions, refreshKey]);

    // Focus edit input when editing starts
    useEffect(() => {
        if (editingSessionId && editInputRef.current) {
            editInputRef.current.focus();
            editInputRef.current.select();
        }
    }, [editingSessionId]);

    /**
     * Save edited title
     */
    const handleSaveEdit = async (sessionId: string, e: React.MouseEvent) => {
        e.stopPropagation();

        if (!editTitle.trim()) {
            dispatch({ type: 'reset' });
            return;
        }

        try {
            await langflowApi.updateSession(sessionId, { title: editTitle.trim() });
            setSessions(prev => prev.map(s =>
                s.id === sessionId ? { ...s, title: editTitle.trim() } : s
            ));
        } catch (err) {
            console.error('Failed to update session title:', err);
        } finally {
            dispatch({ type: 'reset' });
        }
    };

    /**
     * Confirm delete
     */
    const handleConfirmDelete = async (sessionId: string, e: React.MouseEvent) => {
        e.stopPropagation();

        try {
            await langflowApi.deleteSession(sessionId);
            setSessions(prev => prev.filter(s => s.id !== sessionId));
            if (selectedSessionId === sessionId) {
                onSelectSession(null);
            }
        } catch (err) {
            console.error('Failed to delete session:', err);
        } finally {
            dispatch({ type: 'reset' });
        }
    };

    /**
     * Handle session click
     */
    const handleSessionClick = (sessionId: string) => {
        if (interaction.mode !== 'idle') return;
        onSelectSession(sessionId);
    };

    /**
     * Handle clear all chats confirmation
     */
    const handleConfirmClearAll = async () => {
        setClearAllLoading(true);
        try {
            await Promise.all(sessions.map(session => langflowApi.deleteSession(session.id)));
            setSessions([]);
            onSelectSession(null);
        } catch (err) {
            console.error('Failed to clear all chats:', err);
        } finally {
            setClearAllLoading(false);
            setShowClearAllModal(false);
        }
    };

    // Render helpers
    const renderEmptyState = () => (
        <div className="flex flex-col items-center justify-center gap-2 py-12">
            <MessageSquare className="h-8 w-8 text-subtext-color" />
            <span className="text-body font-body text-subtext-color text-center">
                No chat history yet
            </span>
            <span className="text-body-small font-body text-subtext-color text-center">
                Start a new conversation to begin
            </span>
        </div>
    );

    const renderLoadingState = () => (
        <div className="flex items-center justify-center py-12">
            <Loader className="h-6 w-6 animate-spin text-subtext-color" />
        </div>
    );

    const renderErrorState = () => (
        <div className="flex flex-col items-center justify-center gap-2 py-12">
            <AlertCircle className="h-8 w-8 text-error-600" />
            <span className="text-body font-body text-error-600 text-center">{error}</span>
            <Button variant="neutral-secondary" size="small" onClick={loadSessions}>
                Retry
            </Button>
        </div>
    );

    const renderSessionList = () => (
        <div className="flex w-full flex-col items-start gap-4">
            {Array.from(groupSessionsByTime(sessions)).map(([groupLabel, groupSessions], groupIndex) => (
                <React.Fragment key={groupLabel}>
                    {groupIndex > 0 && (
                        <div className="flex h-px w-full flex-none flex-col items-center gap-2 bg-neutral-border" />
                    )}
                    <div className="flex w-full flex-col items-start gap-2">
                        <span className="text-caption-bold font-caption-bold text-subtext-color">
                            {groupLabel}
                        </span>
                        {groupSessions.map((session) => (
                            <SessionItem
                                key={session.id}
                                session={session}
                                isSelected={session.id === selectedSessionId}
                                isDarkTheme={isDarkTheme}
                                isEditing={session.id === editingSessionId}
                                isDeleting={session.id === deletingSessionId}
                                editTitle={editTitle}
                                editInputRef={editInputRef}
                                onEditTitleChange={(title) => dispatch({ type: 'update-title', title })}
                                onStartEdit={(e) => {
                                    e.stopPropagation();
                                    dispatch({ type: 'start-edit', sessionId: session.id, title: getSessionTitle(session) });
                                }}
                                onSaveEdit={(e) => handleSaveEdit(session.id, e)}
                                onCancelEdit={(e) => {
                                    e.stopPropagation();
                                    dispatch({ type: 'reset' });
                                }}
                                onEditKeyDown={(e) => {
                                    if (e.key === 'Enter') {
                                        e.preventDefault();
                                        handleSaveEdit(session.id, e as unknown as React.MouseEvent);
                                    } else if (e.key === 'Escape') {
                                        dispatch({ type: 'reset' });
                                    }
                                }}
                                onStartDelete={(e) => {
                                    e.stopPropagation();
                                    dispatch({ type: 'start-delete', sessionId: session.id });
                                }}
                                onConfirmDelete={(e) => handleConfirmDelete(session.id, e)}
                                onCancelDelete={(e) => {
                                    e.stopPropagation();
                                    dispatch({ type: 'reset' });
                                }}
                                onClick={() => handleSessionClick(session.id)}
                            />
                        ))}
                    </div>
                </React.Fragment>
            ))}
        </div>
    );

    return (
        <div className={`flex h-full w-full flex-col items-start gap-0 ${className}`}>
            {/* Header */}
            <div className={`flex w-full items-center justify-between border-b border-solid  ${isDarkTheme ? 'border-brand-primary' : 'border-neutral-1000'} px-6 py-4`}>
                <div className="flex items-center gap-2 h-8">
                    <History className={`text-heading-3 font-heading-3 ${isDarkTheme ? 'text-brand-primary' : 'text-default-font'}`} />
                    <span className="text-heading-3 font-heading-3 text-default-font">
                        Chat History
                    </span>
                </div>

                <div className="flex items-center gap-1">
                    <IconButton icon={<X />} onClick={onClose} />
                </div>
            </div>

            {/* New Chat Button */}
            <div className="w-full px-4 pt-4">
                <Button
                    className="h-8 w-full"
                    variant="brand-primary"
                    size="medium"
                    icon={<Plus />}
                    onClick={onNewChat}
                >
                    New Chat
                </Button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto w-full px-4 py-4">
                {isLoading ? renderLoadingState() :
                 error ? renderErrorState() :
                 sessions.length === 0 ? renderEmptyState() :
                 renderSessionList()}
            </div>
            
            {/* Footer */}
            <div className="flex w-full items-center justify-between border-t border-solid border-neutral-border px-4 pt-4 pb-4">
                <Button
                    variant="destructive-secondary"
                    size="medium"
                    icon={<Trash2 />}
                    onClick={() => setShowClearAllModal(true)}
                    disabled={sessions.length === 0}
                >
                    Clear History
                </Button>
            </div>

            {/* Clear All Confirmation Modal */}
            <ClearAllDialog
                open={showClearAllModal}
                onClose={() => setShowClearAllModal(false)}
                onConfirm={handleConfirmClearAll}
                sessionCount={sessions.length}
                loading={clearAllLoading}
            />
        </div>
    );
}
