import { useEffect } from 'react';
import { useWebSocket } from '@/contexts/WebSocketContext';
import type { EntityType } from '@/hooks/queryKeys';

/**
 * Subscribe to real-time updates for a specific entity.
 * Automatically subscribes on mount and unsubscribes on unmount.
 *
 * @param entityType - The entity type ('alert' | 'case' | 'task')
 * @param entityId - The numeric entity ID (null to skip)
 * @returns Whether the WebSocket is connected
 */
export function useRealtimeSubscription(
  entityType: EntityType,
  entityId: number | null,
): { isConnected: boolean } {
  const { isConnected, subscribe, unsubscribe } = useWebSocket();

  useEffect(() => {
    if (entityId === null) return;
    subscribe(entityType, entityId);
    return () => unsubscribe(entityType, entityId);
  }, [entityType, entityId, subscribe, unsubscribe]);

  return { isConnected };
}
