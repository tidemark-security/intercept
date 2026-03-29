/**
 * ColumnRail - Resizable vertical rail between columns
 * 
 * A thin vertical rail (6px) positioned at the boundary between columns.
 * Features:
 * - Always visible rail with subtle styling
 * - Chevron icon appears on hover/focus
 * - Click to toggle collapsed/expanded state
 * - Drag to resize (with localStorage persistence)
 * - cursor-col-resize for resize affordance
 * - Brand-primary accent on hover
 * 
 * Design inspiration: VS Code, IntelliJ, Splunk, Kibana split panels
 */

/* eslint-disable react-refresh/only-export-components */

import React, { useCallback, useRef, useState, useEffect } from 'react';


import { ChevronLeft, ChevronRight } from 'lucide-react';
/** localStorage key for persisting AI pane width */
const AI_PANE_COLLAPSED_KEY = 'intercept-ai-pane-collapsed';
const AI_PANE_WIDTH_KEY = 'intercept-ai-pane-width';
const DEFAULT_WIDTH = 512;
const MIN_WIDTH = 320;
const MAX_WIDTH = 800;

export interface ColumnRailProps {
  /** Whether the left column is collapsed */
  collapsed: boolean;
  /** Toggle collapsed state */
  onToggle: () => void;
  /** Current width of the left column (for resize) */
  width?: number;
  /** Callback when width changes via drag */
  onWidthChange?: (width: number) => void;
  /** Whether resize is enabled (default: true) */
  resizable?: boolean;
}

/**
 * Get persisted width from localStorage
 */
export function getPersistedWidth(fallbackWidth: number = DEFAULT_WIDTH): number {
  if (typeof window === 'undefined') return fallbackWidth;
  try {
    const stored = localStorage.getItem(AI_PANE_WIDTH_KEY);
    if (stored) {
      const width = parseInt(stored, 10);
      if (!isNaN(width) && width >= MIN_WIDTH && width <= MAX_WIDTH) {
        return width;
      }
    }
  } catch {
    // localStorage not available
  }
  return fallbackWidth;
}

/**
 * Get persisted AI pane collapsed state from localStorage.
 */
export function getPersistedCollapsedState(fallbackCollapsed: boolean): boolean {
  if (typeof window === 'undefined') return fallbackCollapsed;
  try {
    const stored = localStorage.getItem(AI_PANE_COLLAPSED_KEY);
    if (stored === 'true') return true;
    if (stored === 'false') return false;
  } catch {
    // localStorage not available
  }
  return fallbackCollapsed;
}

/**
 * Persist AI pane collapsed state to localStorage.
 */
export function persistCollapsedState(collapsed: boolean): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(AI_PANE_COLLAPSED_KEY, String(collapsed));
  } catch {
    // localStorage not available
  }
}

/**
 * Persist width to localStorage
 */
function persistWidth(width: number): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(AI_PANE_WIDTH_KEY, String(width));
  } catch {
    // localStorage not available
  }
}

export function ColumnRail({
  collapsed,
  onToggle,
  width,
  onWidthChange,
  resizable = true,
}: ColumnRailProps) {
  const railRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  
  // Use refs to avoid stale closure issues during drag
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);
  const hasDragged = useRef(false);
  const onWidthChangeRef = useRef(onWidthChange);
  
  // Keep ref in sync with prop
  useEffect(() => {
    onWidthChangeRef.current = onWidthChange;
  }, [onWidthChange]);

  // Handle drag start
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (!resizable || collapsed) return;
    
    e.preventDefault();
    e.stopPropagation();
    
    setIsDragging(true);
    hasDragged.current = false;
    dragStartX.current = e.clientX;
    dragStartWidth.current = width ?? DEFAULT_WIDTH;
  }, [resizable, collapsed, width]);

  // Set up document-level drag listeners
  useEffect(() => {
    if (!isDragging) return;

    let lastWidth = dragStartWidth.current;

    const handleMouseMove = (e: MouseEvent) => {
      const delta = e.clientX - dragStartX.current;
      
      // Only consider it a drag if moved more than 3px
      if (Math.abs(delta) > 3) {
        hasDragged.current = true;
      }
      
      lastWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, dragStartWidth.current + delta));
      onWidthChangeRef.current?.(lastWidth);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      
      // Persist the final width after drag
      if (hasDragged.current) {
        persistWidth(lastWidth);
      }
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    
    // Set cursor on body during drag
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isDragging]);

  // Handle keyboard toggle
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onToggle();
    }
  }, [onToggle]);

  // Handle click - only toggle if we didn't drag
  const handleClick = useCallback((e: React.MouseEvent) => {
    // If we dragged, don't toggle
    if (hasDragged.current) {
      e.preventDefault();
      e.stopPropagation();
      hasDragged.current = false;
      return;
    }
    onToggle();
  }, [onToggle]);

  return (
    <div
      ref={railRef}
      role="button"
      tabIndex={0}
      aria-label={collapsed ? 'Expand AI panel' : 'Collapse AI panel'}
      onClick={handleClick}
      onMouseDown={handleMouseDown}
      onKeyDown={handleKeyDown}
      className={`
        group relative flex items-center justify-center shrink-0
        h-full w-1.5
        cursor-col-resize
        transition-colors duration-150
        bg-transparent
        hover:bg-brand-300/15
        focus:outline-none focus-visible:bg-brand-300/15
        ${isDragging ? 'bg-brand-300/25' : ''}
      `}
    >
      {/* Subtle vertical line - always visible */}
      <div 
        className={`
          absolute inset-y-0 left-1/2 -translate-x-1/2 w-px
          transition-colors duration-150
          ${isDragging ? 'bg-brand-primary' : 'bg-neutral-border group-hover:bg-brand-300/50'}
        `}
      />
      
      {/* Chevron - appears on hover/focus, rotates based on collapsed state */}
      <div 
        className={`
          absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2
          flex items-center justify-center
          w-5 h-8 rounded-sm
          bg-neutral-100/90 border border-neutral-border
          opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100
          transition-opacity duration-150
          shadow-sm
          ${isDragging ? 'opacity-100' : ''}
        `}
      >
        {collapsed ? (
          <ChevronRight className="w-4 h-4 text-brand-primary" />
        ) : (
          <ChevronLeft className="w-4 h-4 text-brand-primary" />
        )}
      </div>
    </div>
  );
}

export { MIN_WIDTH, MAX_WIDTH, DEFAULT_WIDTH };
