/**
 * Centralized query configuration for TanStack Query
 * 
 * This file defines cache timing constants to ensure consistent behavior
 * across all entity detail hooks and list views.
 */

export const QUERY_STALE_TIMES = {
  /** 
   * For real-time collaboration - short stale time
   * Use for detail views where multiple analysts may be working simultaneously
   */
  REALTIME: 30 * 1000, // 30 seconds
  
  /** 
   * For mostly-static data that rarely changes
   * Use for reference data, configurations, etc.
   */
  STATIC: 5 * 60 * 1000, // 5 minutes
  
  /** 
   * For list views with pagination
   * Balances freshness with performance
   */
  LIST: 60 * 1000, // 1 minute
} as const;

/**
 * Refetch interval configuration for automatic polling
 * 
 * These intervals control how often TanStack Query will automatically
 * refetch data in the background, even without user interaction.
 */
export const QUERY_REFETCH_INTERVALS = {
  /**
   * For detail views - frequent polling for real-time updates
   */
  DETAIL: 30 * 1000, // 30 seconds
  
  /**
   * For list views - less frequent to reduce API load
   */
  LIST: 60 * 1000, // 60 seconds
  
  /**
   * For active AI triage processing - fast polling to show results quickly
   */
  TRIAGE_ACTIVE: 3 * 1000, // 3 seconds

  /**
   * For active timeline enrichments - short-lived fallback polling to recover from missed realtime updates
   */
  ENRICHMENT_ACTIVE: 3 * 1000, // 3 seconds
} as const;

/**
 * Fallback refetch intervals when WebSocket is connected.
 * Much longer than normal since real-time events handle most updates.
 */
export const QUERY_REFETCH_INTERVALS_WS = {
  /** Detail views: 5 minutes fallback when WS connected */
  DETAIL: 5 * 60 * 1000,
  /** List views: 5 minutes fallback when WS connected */
  LIST: 5 * 60 * 1000,
} as const;
