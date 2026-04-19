/**
 * AI Context
 * 
 * Provides global state management for AI chat functionality:
 * - Active session tracking
 * - Message history
 * - Streaming state
 * - Error handling
 */

import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import * as langflowApi from '../services/langflowApi';

interface Message {
  id: string;
  role: 'USER' | 'ASSISTANT' | 'SYSTEM';
  content: string;
  timestamp: string;
  isStreaming?: boolean;
}

interface AIContextValue {
  sessionId: string | null;
  messages: Message[];
  isLoading: boolean;
  error: string | null;
  
  // Actions
  createSession: () => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  clearError: () => void;
  clearSession: () => void;
}

const AIContext = createContext<AIContextValue | undefined>(undefined);

export function useAI() {
  const context = useContext(AIContext);
  if (!context) {
    throw new Error('useAI must be used within AIProvider');
  }
  return context;
}

interface AIProviderProps {
  children: ReactNode;
}

export function AIProvider({ children }: AIProviderProps) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createSession = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      // flow_id is determined by server settings
      const session = await langflowApi.createSession({});
      setSessionId(session.id);
      
      // Load existing messages if any
      const existingMessages = await langflowApi.getMessages(session.id);
      setMessages(existingMessages.map(msg => ({
        id: msg.id,
        role: msg.role,
        content: msg.content ?? '',
        timestamp: msg.created_at,
      })));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create session');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const sendMessage = useCallback(async (content: string) => {
    if (!sessionId) {
      setError('No active session');
      return;
    }

    setIsLoading(true);
    setError(null);

    // Add user message immediately
    const userMessage: Message = {
      id: `temp-${Date.now()}`,
      role: 'USER',
      content,
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMessage]);

    // Add placeholder for assistant message
    const assistantMessageId = `assistant-${Date.now()}`;
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'ASSISTANT',
      content: '',
      timestamp: new Date().toISOString(),
      isStreaming: true,
    };
    setMessages(prev => [...prev, assistantMessage]);

    try {
      await langflowApi.streamMessage(sessionId, { message: content }, {
        onConnected: () => {
          console.log('SSE connected');
        },
        onMessage: (data) => {
        setMessages(prev => prev.map(msg => 
          msg.id === assistantMessageId
            ? { ...msg, content: msg.content + data.content }
            : msg
          ));
        },
        onComplete: (data) => {
        setMessages(prev => prev.map(msg => 
          msg.id === assistantMessageId
            ? { 
                ...msg,
                  id: data.message_id || msg.id,
                  content: data.content || msg.content,
                  isStreaming: false,
                }
              : msg
          ));

          setIsLoading(false);
        },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message');
      setMessages(prev => prev.filter(msg => msg.id !== assistantMessageId));
      setIsLoading(false);
    }
  }, [sessionId]);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const clearSession = useCallback(() => {
    setSessionId(null);
    setMessages([]);
    setError(null);
    setIsLoading(false);
  }, []);

  const value: AIContextValue = {
    sessionId,
    messages,
    isLoading,
    error,
    createSession,
    sendMessage,
    clearError,
    clearSession,
  };

  return <AIContext.Provider value={value}>{children}</AIContext.Provider>;
}
