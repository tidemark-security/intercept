"use client";
/* eslint-disable react-refresh/only-export-components */
/**
 * Portal Container Context
 * 
 * Provides a container ref for portaled components (Select, DropdownMenu, Tooltip, etc.)
 * when they need to render inside a specific container instead of document.body.
 * 
 * This solves z-index stacking issues when portaled components are inside modals.
 * The modal provides its content element as the portal container, ensuring dropdowns
 * and other portaled content render inside the modal and respect its z-index stacking.
 * 
 * Usage:
 * 1. In a modal/dialog, wrap content with PortalContainerProvider and pass the container ref
 * 2. Portaled components (Select, DropdownMenu, etc.) consume this context via usePortalContainer()
 * 3. If no provider exists, components portal to document.body (default behavior)
 */

import React, { createContext, useContext, useRef, RefObject } from "react";

interface PortalContainerContextValue {
  /** The container element for portaled content. null = use document.body */
  container: HTMLElement | null;
}

const PortalContainerContext = createContext<PortalContainerContextValue>({
  container: null,
});

interface PortalContainerProviderProps {
  /** The container element for portaled content */
  container: HTMLElement | null;
  children: React.ReactNode;
}

/**
 * Provides a portal container for all portaled components within its children.
 * Use this inside dialogs/modals to ensure dropdowns render inside the modal.
 */
export function PortalContainerProvider({
  container,
  children,
}: PortalContainerProviderProps) {
  return (
    <PortalContainerContext.Provider value={{ container }}>
      {children}
    </PortalContainerContext.Provider>
  );
}

/**
 * Hook to get the current portal container.
 * Returns null if no provider exists (components should fall back to document.body).
 */
export function usePortalContainer(): HTMLElement | null {
  const { container } = useContext(PortalContainerContext);
  return container;
}

/**
 * Hook that creates and returns a ref suitable for use as a portal container.
 * Use this in dialog/modal components that want to provide their content as a container.
 */
export function usePortalContainerRef(): RefObject<HTMLDivElement> {
  return useRef<HTMLDivElement>(null);
}

export { PortalContainerContext };
