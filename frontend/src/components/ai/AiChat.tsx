"use client";

import React, { useRef, useEffect, useState, useCallback } from "react";
import { IconButton } from "@/components/buttons/IconButton";

import type { AiChatProps, SuggestedPrompt, AiChatMessage } from "./types";
import { UserMessage } from "./UserMessage";
import { AssistantMessage } from "./AssistantMessage";
import { SuggestedPrompts } from "./SuggestedPrompts";
import { ChatInput } from "./ChatInput";
import * as langflowApi from "../../services/langflowApi";
import { useMessageFeedback } from "@/hooks/useMessageFeedback";
import { useTheme } from "@/contexts/ThemeContext";

import { AlertCircle, RefreshCw, Sparkles, X } from 'lucide-react';
/**
 * Default suggested prompts for NEW chat sessions based on context type.
 * These are initial conversation starters - after the first message,
 * dynamic prompts from AI responses take precedence.
 */
const DEFAULT_PROMPTS: Record<string, SuggestedPrompt[]> = {
  case: [
    { id: "1", label: "Summarize this case" },
    { id: "2", label: "What are the key indicators?" },
    { id: "3", label: "Suggest next steps" },
    { id: "4", label: "Find similar cases" },
  ],
  task: [
    { id: "1", label: "Help me get started" },
    { id: "2", label: "What should I look for?" },
    { id: "3", label: "Suggest an approach" },
    { id: "4", label: "Find related evidence" },
  ],
  alert: [
    { id: "1", label: "Analyze this alert" },
    { id: "2", label: "Is this a true positive?" },
    { id: "3", label: "What's the recommended response?" },
    { id: "4", label: "Find similar alerts" },
  ],
  general: [
    { id: "1", label: "What should I focus on today?" },
    { id: "2", label: "Show me high priority items" },
    { id: "3", label: "Help me investigate an IOC" },
    { id: "4", label: "Search for recent incidents" },
  ],
};

/**
 * Parse suggested prompts from AI response content.
 * Looks for <suggested_prompts>prompt1|prompt2|prompt3</suggested_prompts> tags.
 * Returns cleaned content (without the tag) and extracted prompts.
 */
function parseSuggestedPrompts(content: string): { cleanContent: string; prompts: SuggestedPrompt[] | null } {
  const regex = /<suggested_prompts>(.*?)<\/suggested_prompts>/s;
  const match = content.match(regex);
  
  if (!match) {
    return { cleanContent: content, prompts: null };
  }
  
  const promptsStr = match[1];
  const prompts = promptsStr
    .split('|')
    .map((label, index) => ({
      id: `dynamic-${index}`,
      label: label.trim(),
    }))
    .filter(p => p.label.length > 0);
  
  const cleanContent = content.replace(regex, '').trim();
  
  return { cleanContent, prompts: prompts.length > 0 ? prompts : null };
}

/**
 * AiChat - Reusable AI chat sidebar component with built-in SSE streaming
 * 
 * Features:
 * - Self-contained session and message management
 * - SSE streaming for progressive token display
 * - User and assistant message display
 * - Tool approval requests with approve/deny actions
 * - Message feedback (thumbs up/down)
 * - Copy message functionality
 * - Suggested prompts for quick actions
 * - Message input with send button
 * - Auto-scroll to latest messages
 * - Optional close button for panel dismissal
 * - Error handling with retry
 * 
 * Can be used in two modes:
 * 1. Uncontrolled (default): Component manages its own session/messages via SSE
 * 2. Controlled: Parent provides messages and onSendMessage callback
 * 
 * @example
 * ```tsx
 * // Uncontrolled mode (uses internal SSE streaming)
 * <AiChat
 *   contextType="case"
 *   entityId={caseId}
 *   onClose={handleClose}
 * />
 * 
 * // Controlled mode (parent manages state)
 * <AiChat
 *   messages={messages}
 *   isLoading={isLoading}
 *   onSendMessage={handleSend}
 *   contextType="case"
 *   entityId={caseId}
 *   onClose={handleClose}
 * />
 * ```
 */
export function AiChat({
  title = "AI Assistant",
  messages: externalMessages,
  isLoading: externalIsLoading,
  error: externalError,
  suggestedPrompts,
  inputPlaceholder = "Ask me anything...",
  onSendMessage: externalOnSendMessage,
  onSuggestedPromptClick,
  onClose,
  onToolApprove,
  onToolDeny,
  onFeedbackPositive,
  onFeedbackNegative,
  onCopyMessage,
  contextType = "general",
  entityId,
  entityHumanId,
  username,
  sessionOwnerUsername,
  persistSession,
  initialSessionId,
  onSessionChange,
  isLazy = true,
  showHistoryButton = false,
  onHistoryClick,
  className = "",
}: AiChatProps) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const streamingBufferRef = useRef<Record<string, string>>({});
  const streamingFlushTimerRef = useRef<number | null>(null);
  const scrollDebounceTimerRef = useRef<number | null>(null);
  const wasStreamingRef = useRef(false);
  const prevMessageCountRef = useRef(0);
  
  // Ref to prevent race conditions during session creation
  const creatingSessionRef = useRef(false);
  
  // Store pending message if user sends before session is created
  const pendingMessageRef = useRef<string | null>(null);

  const flushStreamingBuffer = useCallback((assistantMessageId: string) => {
    const buffered = streamingBufferRef.current[assistantMessageId];
    if (!buffered) return;

    setInternalMessages(prev => prev.map(msg =>
      msg.id === assistantMessageId
        ? { ...msg, content: msg.content + buffered }
        : msg
    ));

    streamingBufferRef.current[assistantMessageId] = '';
  }, []);

  const stopStreamingFlushTimer = useCallback(() => {
    if (streamingFlushTimerRef.current !== null) {
      window.clearInterval(streamingFlushTimerRef.current);
      streamingFlushTimerRef.current = null;
    }
  }, []);
  
  // Determine if we're in controlled mode (parent provides messages and handler)
  const isControlled = externalMessages !== undefined && externalOnSendMessage !== undefined;

  // Determine if session should be persisted (default true for entity-specific contexts)
  const shouldPersistSession = persistSession ?? (contextType !== 'general' && entityId !== undefined);
  
  // Generate storage key for session persistence
  const sessionStorageKey = shouldPersistSession && entityId !== undefined
    ? `ai-chat-session-${contextType}-${entityId}`
    : null;

  // Internal state for uncontrolled mode
  const [sessionId, setSessionId] = useState<string | null>(() => {
    // If initialSessionId is provided, use it
    if (initialSessionId) {
      return initialSessionId;
    }
    // Try to restore session from localStorage on initial render
    if (sessionStorageKey && typeof window !== 'undefined') {
      return localStorage.getItem(sessionStorageKey);
    }
    return null;
  });
  const [internalMessages, setInternalMessages] = useState<AiChatMessage[]>([]);
  const [internalIsLoading, setInternalIsLoading] = useState(false);
  const [internalError, setInternalError] = useState<string | null>(null);
  const [isInitializing, setIsInitializing] = useState(!isControlled);
  
  // Dynamic prompts extracted from AI responses (takes priority over defaults)
  const [dynamicPrompts, setDynamicPrompts] = useState<SuggestedPrompt[] | null>(null);
  
  // Track if we've already initialized to prevent double initialization
  const hasInitializedRef = useRef(false);

  // Message feedback hook for API persistence
  const { setFeedback } = useMessageFeedback();
  
  // Handle feedback with API persistence when running in uncontrolled mode
  const handleFeedbackPositive = useCallback((messageId: string) => {
    // Call external handler if provided
    onFeedbackPositive?.(messageId);
    
    // Persist to API (works in both controlled and uncontrolled modes)
    setFeedback({ messageId, feedback: 'POSITIVE' });
    
    // Update local state to reflect feedback
    if (!isControlled) {
      setInternalMessages(prev => prev.map(msg =>
        msg.id === messageId ? { ...msg, feedback: 'positive' } : msg
      ));
    }
  }, [onFeedbackPositive, setFeedback, isControlled]);

  const handleFeedbackNegative = useCallback((messageId: string) => {
    // Call external handler if provided
    onFeedbackNegative?.(messageId);
    
    // Persist to API
    setFeedback({ messageId, feedback: 'NEGATIVE' });
    
    // Update local state to reflect feedback
    if (!isControlled) {
      setInternalMessages(prev => prev.map(msg =>
        msg.id === messageId ? { ...msg, feedback: 'negative' } : msg
      ));
    }
  }, [onFeedbackNegative, setFeedback, isControlled]);

  // Use external or internal state based on mode
  const messages = isControlled ? externalMessages : internalMessages;
  const isLoading = isControlled ? (externalIsLoading ?? false) : internalIsLoading;
  const error = isControlled ? externalError : internalError;

  // Use dynamic prompts from AI response after first message, or defaults only for new/blank chats
  const effectivePrompts = messages.length === 0
    ? (suggestedPrompts ?? DEFAULT_PROMPTS[contextType] ?? DEFAULT_PROMPTS.general)
    : (dynamicPrompts ?? []);

  /**
   * Load messages for an existing session
   */
  const loadSessionMessages = useCallback(async (existingSessionId: string) => {
    try {
      const existingMessages = await langflowApi.getMessages(existingSessionId, sessionOwnerUsername);
      
      // Parse and clean messages, extracting prompts from the last assistant message
      let extractedPrompts: SuggestedPrompt[] | null = null;
      const mappedMessages = existingMessages.map((msg, index) => {
        const isAssistant = msg.role !== 'USER';
        let content = msg.content ?? '';
        
        if (isAssistant) {
          const { cleanContent, prompts } = parseSuggestedPrompts(content);
          content = cleanContent;
          
          // Only keep prompts from the last assistant message
          const isLastAssistant = !existingMessages.slice(index + 1).some(m => m.role !== 'USER');
          if (isLastAssistant && prompts) {
            extractedPrompts = prompts;
          }
        }
        
        return {
          id: msg.id,
          role: (msg.role === 'USER' ? 'user' : 'assistant') as 'user' | 'assistant',
          content,
          timestamp: new Date(msg.created_at),
        };
      });
      
      setInternalMessages(mappedMessages);
      setDynamicPrompts(extractedPrompts);
      return true;
    } catch (err) {
      // Session may have expired or been deleted
      console.warn('Failed to load existing session messages:', err);
      return false;
    }
  }, [sessionOwnerUsername]);

  /**
   * Build the LangFlow context (tweaks) payload for entity-aware conversations.
   * This follows LangFlow's expected format where each tweak is an object with input_value.
   * Always includes username and entity_id for consistency across all flows.
   */
  const buildLangFlowContext = useCallback((): Record<string, any> => {
    const context: Record<string, { input_value: string }> = {};

    // Always include username (empty string if not provided)
    context.username = { input_value: username || '' };

    // Always include entity_id (empty string if not provided)
    context.entity_id = { input_value: entityHumanId || '' };

    // Include entity_type for non-general contexts
    if (contextType && contextType !== 'general') {
      context.entity_type = { input_value: contextType };
    }

    return context;
  }, [entityHumanId, username, contextType]);

  /**
   * Generate a session title from the first message.
   * Format: "{entityHumanId}: {truncatedMsg}" for entity contexts, else just "{truncatedMsg}"
   */
  const generateSessionTitle = useCallback((firstMessage: string): string => {
    const maxLength = 100;
    let title = firstMessage.trim().replace(/\s+/g, ' ');
    
    if (title.length > maxLength) {
      title = title.slice(0, maxLength).trimEnd() + '…';
    }
    
    // For entity-specific contexts, prefix with entity ID
    if (contextType !== 'general' && entityHumanId) {
      return `${entityHumanId}: ${title}`;
    }
    
    return title;
  }, [contextType, entityHumanId]);

  /**
   * Create a new chat session
   * @param title Optional title for the session (used in lazy creation)
   */
  const createSession = useCallback(async (title?: string): Promise<string | null> => {
    // Prevent concurrent session creation
    if (creatingSessionRef.current) {
      return null;
    }
    creatingSessionRef.current = true;
    
    setIsInitializing(true);
    setInternalError(null);
    
    try {
      // Build context with entity information for LangFlow
      const context = buildLangFlowContext();
      
      // Pass context_type so backend can select the appropriate flow from settings
      const session = await langflowApi.createSession({ 
        context, 
        title,
        context_type: contextType,
      });
      setSessionId(session.id);
      
      // Persist session ID to localStorage if enabled
      if (sessionStorageKey) {
        localStorage.setItem(sessionStorageKey, session.id);
      }
      
      return session.id;
    } catch (err) {
      setInternalError(err instanceof Error ? err.message : 'Failed to create session');
      return null;
    } finally {
      setIsInitializing(false);
      creatingSessionRef.current = false;
    }
  }, [sessionStorageKey, buildLangFlowContext, contextType]);

  /**
   * Try to resume an existing session or prepare for lazy creation
   */
  const initializeSession = useCallback(async () => {
    setIsInitializing(true);
    setInternalError(null);
    
    // If we have a stored session ID, try to resume it
    if (sessionId) {
      const loaded = await loadSessionMessages(sessionId);
      if (loaded) {
        setIsInitializing(false);
        return;
      }
      // Session was invalid, clear it
      if (sessionStorageKey) {
        localStorage.removeItem(sessionStorageKey);
      }
      setSessionId(null);
    }
    
    // In lazy mode, don't create session until first message
    if (isLazy) {
      setIsInitializing(false);
      return;
    }
    
    // For entity-specific contexts in non-lazy mode, wait for entityHumanId before creating new session
    // This ensures the context is complete when sent to LangFlow
    if (contextType !== 'general' && !entityHumanId) {
      // Don't create session yet - keep isInitializing true
      // The useEffect will re-trigger when entityHumanId becomes available
      return;
    }
    
    // Create a new session (non-lazy mode only)
    await createSession();
  }, [sessionId, sessionStorageKey, loadSessionMessages, createSession, contextType, entityHumanId, isLazy]);

  /**
   * Send a message using SSE streaming (uncontrolled mode)
   * If no session exists (lazy mode), creates one first using the message as the title source.
   */
  const sendMessageInternal = useCallback(async (content: string) => {
    let activeSessionId = sessionId;
    
    // Lazy session creation: create session on first message
    if (!activeSessionId) {
      // Prevent sending if already creating a session
      if (creatingSessionRef.current) {
        pendingMessageRef.current = content;
        return;
      }
      
      // Generate title from this first message
      const title = generateSessionTitle(content);
      activeSessionId = await createSession(title);
      
      if (!activeSessionId) {
        // Session creation failed, error already set by createSession
        return;
      }
      
      // Notify parent about new session
      onSessionChange?.(activeSessionId);
    }

    setInternalIsLoading(true);
    setInternalError(null);
    
    // Clear dynamic prompts when user sends a new message
    setDynamicPrompts(null);

    // Add user message immediately
    const userMessage: AiChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date(),
    };
    setInternalMessages(prev => [...prev, userMessage]);

    // Add placeholder for assistant message
    const assistantMessageId = `assistant-${Date.now()}`;
    const assistantMessage: AiChatMessage = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
    };
    setInternalMessages(prev => [...prev, assistantMessage]);

    try {
      // Create SSE connection for streaming
      const eventSource = langflowApi.createStreamConnection(activeSessionId, content);

      eventSource.addEventListener('connected', () => {
        console.log('SSE connected');
      });

      eventSource.addEventListener('message', (event) => {
        const data = JSON.parse(event.data);

        streamingBufferRef.current[assistantMessageId] =
          (streamingBufferRef.current[assistantMessageId] || '') + data.content;

        if (streamingFlushTimerRef.current === null) {
          streamingFlushTimerRef.current = window.setInterval(() => {
            flushStreamingBuffer(assistantMessageId);
          }, 60);
        }
      });

      eventSource.addEventListener('complete', (event) => {
        const data = JSON.parse(event.data);

        flushStreamingBuffer(assistantMessageId);
        stopStreamingFlushTimer();
        delete streamingBufferRef.current[assistantMessageId];
        
        // Parse suggested prompts from content
        const { cleanContent, prompts } = parseSuggestedPrompts(data.content);
        
        // Update dynamic prompts if AI provided new ones
        if (prompts) {
          setDynamicPrompts(prompts);
        }
        
        // Update with final message (cleaned) and remove streaming flag
        setInternalMessages(prev => prev.map(msg => 
          msg.id === assistantMessageId
            ? { 
                ...msg,
                id: data.message_id || msg.id,
                content: cleanContent,
                isStreaming: false,
              }
            : msg
        ));
        
        eventSource.close();
        setInternalIsLoading(false);
      });

      eventSource.addEventListener('error', (event: Event) => {
        const messageEvent = event as MessageEvent;
        const data = messageEvent.data ? JSON.parse(messageEvent.data) : { error: 'Stream error' };
        setInternalError(data.error || 'Failed to receive response');

        stopStreamingFlushTimer();
        delete streamingBufferRef.current[assistantMessageId];
        
        // Remove streaming message on error
        setInternalMessages(prev => prev.filter(msg => msg.id !== assistantMessageId));
        
        eventSource.close();
        setInternalIsLoading(false);
      });

      eventSource.onerror = () => {
        setInternalError('Connection error');
        stopStreamingFlushTimer();
        delete streamingBufferRef.current[assistantMessageId];
        setInternalMessages(prev => prev.filter(msg => msg.id !== assistantMessageId));
        eventSource.close();
        setInternalIsLoading(false);
      };

    } catch (err) {
      setInternalError(err instanceof Error ? err.message : 'Failed to send message');
      stopStreamingFlushTimer();
      delete streamingBufferRef.current[assistantMessageId];
      setInternalMessages(prev => prev.filter(msg => msg.id !== assistantMessageId));
      setInternalIsLoading(false);
    }
  }, [sessionId, createSession, generateSessionTitle, onSessionChange, flushStreamingBuffer, stopStreamingFlushTimer]);

  /**
   * Handle sending a message (routes to internal or external handler)
   */
  const handleSendMessage = useCallback((content: string) => {
    if (isControlled && externalOnSendMessage) {
      externalOnSendMessage(content);
    } else {
      sendMessageInternal(content);
    }
  }, [isControlled, externalOnSendMessage, sendMessageInternal]);

  /**
   * Clear error and optionally retry session creation
   */
  const handleRetry = useCallback(() => {
    setInternalError(null);
    // Reset initialization flag to allow retry
    hasInitializedRef.current = false;
    initializeSession();
  }, [initializeSession]);

  // Initialize session on mount if in uncontrolled mode
  // For entity-specific contexts, also re-trigger when entityHumanId becomes available
  useEffect(() => {
    if (isControlled) return;
    
    // First initialization
    if (!hasInitializedRef.current) {
      hasInitializedRef.current = true;
      initializeSession();
      return;
    }
    
    // Re-trigger if we're still initializing (waiting for entity data) and now have entityHumanId
    if (isInitializing && !sessionId && entityHumanId) {
      initializeSession();
    }
  }, [isControlled, initializeSession, isInitializing, sessionId, entityHumanId]);

  // Handle when initialSessionId prop changes from parent (e.g., selecting different history item)
  useEffect(() => {
    if (isControlled) return;
    
    // If initialSessionId changed and is different from current session
    if (initialSessionId && initialSessionId !== sessionId) {
      setSessionId(initialSessionId);
      setInternalMessages([]);
      prevMessageCountRef.current = 0;
      setIsInitializing(true);
      loadSessionMessages(initialSessionId).then((loaded) => {
        if (!loaded) {
          setInternalError('Failed to load session');
        }
        setIsInitializing(false);
      });
    } else if (initialSessionId === null && sessionId) {
      // Parent cleared the session (e.g., "New Chat")
      // In lazy mode, just clear state without creating a new session
      setSessionId(null);
      setInternalMessages([]);
      prevMessageCountRef.current = 0;
      setDynamicPrompts(null); // Reset to default prompts
      hasInitializedRef.current = true; // Prevent re-initialization
      setIsInitializing(false);
      
      // Only create session immediately if not in lazy mode
      if (!isLazy) {
        hasInitializedRef.current = false;
        createSession();
      }
    }
  }, [createSession, initialSessionId, isControlled, isLazy, loadSessionMessages, sessionId]);

  // Notify parent when session changes
  useEffect(() => {
    if (onSessionChange) {
      onSessionChange(sessionId);
    }
  }, [sessionId, onSessionChange]);

  // Auto-scroll to bottom only when new messages arrive or streaming completes
  useEffect(() => {
    const messageCount = messages.length;
    const hasStreamingMessage = messages.some(m => m.isStreaming);
    const wasStreaming = wasStreamingRef.current;
    const prevMessageCount = prevMessageCountRef.current;
    
    // Update refs for next render
    wasStreamingRef.current = hasStreamingMessage;
    prevMessageCountRef.current = messageCount;

    const scrollToBottom = (behavior: ScrollBehavior = "smooth") => {
      messagesEndRef.current?.scrollIntoView({ behavior, block: "end" });
    };

    // Clear any pending debounced scroll
    if (scrollDebounceTimerRef.current !== null) {
      window.clearTimeout(scrollDebounceTimerRef.current);
      scrollDebounceTimerRef.current = null;
    }

    // Determine if we should scroll:
    // 1. New message added (count increased)
    // 2. Streaming just finished (wasStreaming && !hasStreamingMessage)
    const isNewMessage = messageCount > prevMessageCount;
    const streamingJustFinished = wasStreaming && !hasStreamingMessage;
    
    if (!isNewMessage && !streamingJustFinished) {
      // Message updated in place (e.g., feedback) - don't scroll
      return;
    }

    if (hasStreamingMessage) {
      // Debounce scroll during streaming (scroll at most every 300ms)
      scrollDebounceTimerRef.current = window.setTimeout(() => {
        scrollToBottom("auto");
        scrollDebounceTimerRef.current = null;
      }, 300);
    } else if (streamingJustFinished) {
      // Final scroll when streaming just stopped - delayed to allow Mermaid/async content to render
      scrollDebounceTimerRef.current = window.setTimeout(() => {
        scrollToBottom("smooth");
        scrollDebounceTimerRef.current = null;
      }, 150);
    } else if (isNewMessage) {
      // New non-streaming message - immediate, smooth
      scrollToBottom("smooth");
    }

    return () => {
      if (scrollDebounceTimerRef.current !== null) {
        window.clearTimeout(scrollDebounceTimerRef.current);
      }
    };
  }, [messages]);

  useEffect(() => {
    return () => {
      stopStreamingFlushTimer();
      if (scrollDebounceTimerRef.current !== null) {
        window.clearTimeout(scrollDebounceTimerRef.current);
      }
    };
  }, [stopStreamingFlushTimer]);

  // Handle suggested prompt click
  const handlePromptClick = (prompt: SuggestedPrompt) => {
    if (onSuggestedPromptClick) {
      onSuggestedPromptClick(prompt);
    } else {
      // Default behavior: send prompt label as message
      handleSendMessage(prompt.label);
    }
  };

  // Determine input placeholder based on state
  const getPlaceholder = () => {
    if (isInitializing) return "Initializing...";
    if (isLoading) return "Waiting for response...";
    return inputPlaceholder;
  };

  // Determine if input should be disabled
  // In lazy mode, allow input even without a session (session will be created on first message)
  const isInputDisabled = isInitializing || !!error;

  return (
    <div className={`flex h-full w-full flex-col items-start gap-0 ${className}`}>
      {/* Header */}
      <div className={`flex w-full items-center justify-between border-b border-solid ${isDarkTheme ? 'border-brand-primary' : 'border-neutral-1000'} px-6 py-4`}>
        <div className="flex items-center gap-2 h-8">
          <Sparkles className={`text-heading-3 font-heading-3 ${isDarkTheme ? 'text-brand-primary' : 'text-default-font'}`} />
          <span className="text-heading-3 font-heading-3 text-default-font">
            {title}
          </span>
          {/* Session indicator for uncontrolled mode */}
          {!isControlled && sessionId && (
            <span className="text-caption font-caption text-subtext-color">
              ({sessionId.slice(0, 8)}...)
            </span>
          )}
        </div>
        {onClose && (
          <IconButton
            icon={<X />}
            onClick={onClose}
          />
        )}
      </div>

      {/* Messages Container */}
      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-4 overflow-auto px-6 pb-0 pt-6">
        {/* Empty state */}
        {messages.length === 0 && !error && !isInitializing && (
          <div className="flex w-full flex-1 items-center justify-center">
            <div className="text-center text-subtext-color">
              <p className="text-body font-body">Start a conversation</p>
              <p className="text-caption font-caption mt-1">
                Ask me anything about your security {contextType === 'general' ? 'investigations' : contextType}
              </p>
            </div>
          </div>
        )}

        {messages.map((message) => (
          message.role === "user" ? (
            <UserMessage key={message.id} message={message} />
          ) : (
            <AssistantMessage
              key={message.id}
              message={message}
              onToolApprove={onToolApprove}
              onToolDeny={onToolDeny}
              onFeedbackPositive={handleFeedbackPositive}
              onFeedbackNegative={handleFeedbackNegative}
              onCopyMessage={onCopyMessage}
            />
          )
        ))}
        
        {/* Error display */}
        {error && (
          <div className="flex w-full items-center gap-3 rounded-lg border border-error-200 bg-error-50 p-6">
            <AlertCircle className="h-5 w-5 flex-shrink-0 text-error-500" />
            <div className="flex-1">
              <p className="text-body-bold font-body-bold text-error-900">Error</p>
              <p className="text-caption font-caption text-error-700 mt-1">{error}</p>
            </div>
            {!isControlled && (
              <button
                onClick={handleRetry}
                className="flex items-center gap-2 rounded px-3 py-1 text-caption font-caption bg-error-100 text-error-900 transition-colors hover:bg-error-200"
              >
                <RefreshCw className="h-4 w-4" />
                Retry
              </button>
            )}
          </div>
        )}
        
        {/* Loading indicator (only shown when no streaming message visible) */}
        {isLoading && !messages.some(m => m.isStreaming) && (
          <div className="flex w-full items-center gap-2 px-3 py-2">
            <div className="flex items-center gap-1">
              <div className={`h-2 w-2 animate-bounce rounded-full ${isDarkTheme ? 'bg-brand-primary' : 'bg-default-font'}`} style={{ animationDelay: "0ms" }} />
              <div className={`h-2 w-2 animate-bounce rounded-full ${isDarkTheme ? 'bg-brand-primary' : 'bg-default-font'}`} style={{ animationDelay: "150ms" }} />
              <div className={`h-2 w-2 animate-bounce rounded-full ${isDarkTheme ? 'bg-brand-primary' : 'bg-default-font'}`} style={{ animationDelay: "300ms" }} />
            </div>
            <span className="text-caption font-caption text-subtext-color">AI is thinking...</span>
          </div>
        )}
        
        {/* Scroll anchor */}
        <div ref={messagesEndRef} />
      </div>

      { /* Input and Suggested Prompts Container */ }
      <div className="flex items-center gap-6 flex-col w-full py-6 px-6 border-t border-solid border-neutral-border">
        {/* Suggested Prompts - hidden while waiting for response */}
        {effectivePrompts.length > 0 && !isLoading && (
          <div className="-mt-2 w-full p-0">
            <SuggestedPrompts prompts={effectivePrompts} onPromptClick={handlePromptClick}/>
          </div>
        )}

        {/* Input */}
        <ChatInput
          placeholder={getPlaceholder()}
          isLoading={isLoading}
          disabled={isInputDisabled}
          onSendMessage={handleSendMessage}
          showHistoryButton={showHistoryButton}
          onHistoryClick={onHistoryClick}
        />
      </div>
    </div>
  );
}

export default AiChat;
