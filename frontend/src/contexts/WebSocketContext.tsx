import React, { createContext, useContext, useEffect, useRef, useCallback, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useSession } from './sessionContext';
import { useToast } from './ToastContext';
import { queryKeys } from '@/hooks/queryKeys';
import type { EntityType } from '@/hooks/queryKeys';
import { OpenAPI } from '@/types/generated/core/OpenAPI';

type RealtimeEventPayload = {
  entity_type: string;
  entity_id: number;
  event_type: string;
  performed_by?: string | null;
  item_id?: string | null;
  item_type?: string | null;
};

type PresencePayload = {
  entity_type: string;
  entity_id: number;
  viewers?: string[];
};

interface WebSocketContextValue {
  /** Whether the WebSocket is currently connected */
  isConnected: boolean;
  /** Subscribe to real-time updates for an entity */
  subscribe: (entityType: EntityType, entityId: number) => void;
  /** Unsubscribe from real-time updates for an entity */
  unsubscribe: (entityType: EntityType, entityId: number) => void;
  /** Get current viewers for an entity */
  getPresence: (entityType: EntityType, entityId: number | null) => string[];
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

function getEntityKey(entityType: string, entityId: number): string {
  return `${entityType}:${entityId}`;
}

function formatItemType(itemType?: string | null): string {
  if (!itemType) return 'timeline item';
  return itemType.replace(/_/g, ' ');
}

function getArticle(noun: string): string {
  return /^[aeiou]/i.test(noun) ? 'an' : 'a';
}

function getRealtimeToastTitle(payload: RealtimeEventPayload): string | null {
  const actor = payload.performed_by;
  if (!actor) return null;

  if (payload.event_type === 'timeline_graph_updated') {
    return `${actor} changed the graph`;
  }

  const itemType = formatItemType(payload.item_type);
  const article = getArticle(itemType);

  if (payload.event_type === 'timeline_item_added') {
    return `${actor} added ${article} ${itemType}`;
  }

  if (payload.event_type === 'timeline_item_updated') {
    return `${actor} updated ${article} ${itemType}`;
  }

  if (payload.event_type === 'timeline_item_deleted') {
    return `${actor} deleted ${article} ${itemType}`;
  }

  return null;
}

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const { status, user } = useSession();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [presenceByKey, setPresenceByKey] = useState<Record<string, string[]>>({});
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const pendingSubscriptions = useRef<Set<string>>(new Set());
  const mountedRef = useRef(true);
  const currentUsername = user?.username ?? null;

  const invalidateEntity = useCallback(
    (entityType: string, entityId: number, eventType?: string) => {
      const type = entityType as EntityType;
      if (eventType === 'timeline_graph_updated') {
        if (type === 'case') {
          queryClient.invalidateQueries({ queryKey: queryKeys.case.graphBase(entityId), exact: false });
        } else if (type === 'task') {
          queryClient.invalidateQueries({ queryKey: queryKeys.task.graphBase(entityId), exact: false });
        }
        return;
      }

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
          const payload = msg.payload as RealtimeEventPayload;
          console.log('[WS] Event received:', payload.entity_type, payload.entity_id, payload.event_type);
          invalidateEntity(payload.entity_type, payload.entity_id, payload.event_type);

          const eventKey = getEntityKey(payload.entity_type, payload.entity_id);
          const isSubscribedToEntity = pendingSubscriptions.current.has(eventKey);
          const isCurrentUserEvent = Boolean(
            currentUsername &&
            payload.performed_by &&
            payload.performed_by.toLowerCase() === currentUsername.toLowerCase(),
          );
          const toastTitle = isSubscribedToEntity && !isCurrentUserEvent
            ? getRealtimeToastTitle(payload)
            : null;

          if (toastTitle) {
            showToast(toastTitle, undefined, 'neutral');
          }
        } else if (msg.type === 'presence' && msg.payload) {
          const payload = msg.payload as PresencePayload;
          if (typeof payload.entity_id === 'number' && payload.entity_type) {
            const key = getEntityKey(payload.entity_type, payload.entity_id);
            setPresenceByKey((current) => ({
              ...current,
              [key]: Array.isArray(payload.viewers) ? payload.viewers : [],
            }));
          }
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
      setPresenceByKey({});
      if (!mountedRef.current) return;
      // Reconnect with exponential backoff
      const delay = reconnectDelayRef.current;
      reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY);
      reconnectTimerRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      // onclose will fire after onerror, triggering reconnect
    };
  }, [currentUsername, invalidateEntity, showToast]);

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
      setPresenceByKey({});
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
    const key = getEntityKey(entityType, entityId);
    pendingSubscriptions.current.delete(key);
    setPresenceByKey((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'unsubscribe', entity_type: entityType, entity_id: entityId }));
    }
  }, []);

  const getPresence = useCallback((entityType: EntityType, entityId: number | null) => {
    if (entityId === null) return [];
    return presenceByKey[getEntityKey(entityType, entityId)] ?? [];
  }, [presenceByKey]);

  const value: WebSocketContextValue = { isConnected, subscribe, unsubscribe, getPresence };

  return <WebSocketContext.Provider value={value}>{children}</WebSocketContext.Provider>;
}

export function usePresence(entityType: EntityType, entityId: number | null): string[] {
  const { getPresence } = useWebSocket();
  return getPresence(entityType, entityId);
}

export function useWebSocket(): WebSocketContextValue {
  const ctx = useContext(WebSocketContext);
  if (!ctx) {
    throw new Error('useWebSocket must be used within a WebSocketProvider');
  }
  return ctx;
}
