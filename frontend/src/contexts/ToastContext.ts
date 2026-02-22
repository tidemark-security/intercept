/**
 * Toast Notification Context
 * 
 * Provides a simple toast notification system for displaying temporary messages.
 * Toasts automatically dismiss after 4 seconds.
 */

import { createContext, useContext } from 'react';

export type ToastVariant = 'brand' | 'neutral' | 'error' | 'success';

export interface ToastData {
  id: string;
  title: string;
  description?: string;
  variant?: ToastVariant;
  duration?: number;
}

export interface ToastContextValue {
  showToast: (title: string, description?: string, variant?: ToastVariant, duration?: number) => void;
  hideToast: (id: string) => void;
}

export const ToastContext = createContext<ToastContextValue | undefined>(undefined);

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}
