import React, { createContext, useContext, useEffect, useRef, useCallback, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useSession } from './sessionContext';
import { queryKeys } from '@/hooks/queryKeys';
import type { EntityType } from '@/hooks/queryKeys';
import { OpenAPI } from '@/types/generated/core/OpenAPI';

interface WebSocketContextValue {
  /** Whether the WebSocket is currently connected */
  isConnected: boolean;
  /** Subscribe to real-time updates for an entity */
  subscribe: (entityType: EntityType, entityId: number) => void;
  /** Unsubscribe from real-time updates for an entity */
  unsubscribe: (entityType: EntityType, entityId: number) => void;
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

function getWsUrl(): string {
  // Derive WebSocket URL from the API base URL (same host:port as REST API)
  const base = OpenAPI.BASE || window.location.origin;
  const wsBase = base.replace(/^http/, 'ws');
  return `${wsBase}/api/v1/ws`;
}

const INITIAL_RECONNECT_DELAY = 1000;
const MAX_RECONNECT_DELAY = 30000;

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const { status } = useSession();
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const pendingSubscriptions = useRef<Set<string>>(new Set());
  const mountedRef = useRef(true);

  const invalidateEntity = useCallback(
    (entityType: string, entityId: number) => {
      const type = entityType as EntityType;
      // Invalidate detail query
      switch (type) {
        case 'alert':
          queryClient.invalidateQueries({ queryKey: queryKeys.alert.detailBase(entityId), exact: false });
          queryClient.invalidateQueries({ queryKey: queryKeys.alert.listBase(), exact: false });
          break;
        case 'case':
          queryClient.invalidateQueries({ queryKey: queryKeys.case.detailBase(entityId), exact: false });
          queryClient.invalidateQueries({ queryKey: queryKeys.case.listBase(), exact: false });
          break;
        case 'task':
          queryClient.invalidateQueries({ queryKey: queryKeys.task.detailBase(entityId), exact: false });
          queryClient.invalidateQueries({ queryKey: queryKeys.task.listBase(), exact: false });
          break;
      }
    },
    [queryClient],
  );

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN || wsRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    const ws = new WebSocket(getWsUrl());
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[WS] Connected to', getWsUrl());
      setIsConnected(true);
      reconnectDelayRef.current = INITIAL_RECONNECT_DELAY;
      // Re-send any pending subscriptions
      for (const key of pendingSubscriptions.current) {
        const [entityType, entityId] = key.split(':');
        ws.send(JSON.stringify({ type: 'subscribe', entity_type: entityType, entity_id: Number(entityId) }));
      }
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'event' && msg.payload) {
          console.log('[WS] Event received:', msg.payload.entity_type, msg.payload.entity_id, msg.payload.event_type);
          invalidateEntity(msg.payload.entity_type, msg.payload.entity_id);
        } else if (msg.type === 'ping') {
          ws.send(JSON.stringify({ type: 'pong' }));
        }
        // subscribed, unsubscribed, pong, error — no special handling needed
      } catch {
        // Ignore parse errors
      }
    };

    ws.onclose = (event) => {
      console.log('[WS] Disconnected, code:', event.code, event.reason);
      setIsConnected(false);
      wsRef.current = null;
      if (!mountedRef.current) return;
      // Reconnect with exponential backoff
      const delay = reconnectDelayRef.current;
      reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY);
      reconnectTimerRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      // onclose will fire after onerror, triggering reconnect
    };
  }, [invalidateEntity]);

  // Connect when authenticated, disconnect when not
  useEffect(() => {
    mountedRef.current = true;
    if (status === 'authenticated') {
      connect();
    }
    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
      wsRef.current = null;
      setIsConnected(false);
    };
  }, [status, connect]);

  const subscribe = useCallback((entityType: EntityType, entityId: number) => {
    const key = `${entityType}:${entityId}`;
    pendingSubscriptions.current.add(key);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[WS] Subscribe:', key);
      wsRef.current.send(JSON.stringify({ type: 'subscribe', entity_type: entityType, entity_id: entityId }));
    }
  }, []);

  const unsubscribe = useCallback((entityType: EntityType, entityId: number) => {
    const key = `${entityType}:${entityId}`;
    pendingSubscriptions.current.delete(key);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'unsubscribe', entity_type: entityType, entity_id: entityId }));
    }
  }, []);

  const value: WebSocketContextValue = { isConnected, subscribe, unsubscribe };

  return <WebSocketContext.Provider value={value}>{children}</WebSocketContext.Provider>;
}

export function useWebSocket(): WebSocketContextValue {
  const ctx = useContext(WebSocketContext);
  if (!ctx) {
    throw new Error('useWebSocket must be used within a WebSocketProvider');
  }
  return ctx;
}
