import React, { useCallback, useState } from "react";

import { Toast } from "@/components/feedback/Toast";
import { ToastContext, ToastData, ToastVariant } from "./ToastContext";

import { AlertCircle, CheckCircle, Info, X } from 'lucide-react';
interface ToastProviderProps {
  children: React.ReactNode;
}

export function ToastProvider({ children }: ToastProviderProps) {
  const [toasts, setToasts] = useState<ToastData[]>([]);

  const getToastDisplayVariant = (variant: ToastVariant): "neutral" | "error" | "success" => {
    if (variant === "brand") {
      return "neutral";
    }

    return variant;
  };

  const showToast = useCallback((
    title: string,
    description?: string,
    variant: ToastVariant = "neutral",
    duration = 4000
  ) => {
    const id = Math.random().toString(36).substring(7);

    setToasts((prev) => {
      const isDuplicate = prev.some(
        (t) => t.title === title && t.description === description && t.variant === variant
      );

      if (isDuplicate) {
        return prev;
      }

      const toast: ToastData = { id, title, description, variant, duration };
      return [...prev, toast];
    });

    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, duration);
  }, []);

  const hideToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const getIcon = (variant: ToastVariant) => {
    switch (variant) {
      case "success":
        return <CheckCircle />;
      case "error":
        return <AlertCircle />;
      case "brand":
        return <Info />;
      default:
        return <Info />;
    }
  };

  return (
    <ToastContext.Provider value={{ showToast, hideToast }}>
      {children}
      {toasts.length > 0 && (
        <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
          {toasts.map((toast) => (
            <div key={toast.id} className="animate-in slide-in-from-right">
              <Toast
                variant={getToastDisplayVariant(toast.variant || "neutral")}
                icon={getIcon(toast.variant || "neutral")}
                title={toast.title}
                description={toast.description}
                actions={
                  <button
                    onClick={() => hideToast(toast.id)}
                    className="p-1 rounded hover:bg-neutral-100"
                  >
                    <X className="h-4 w-4" />
                  </button>
                }
              />
            </div>
          ))}
        </div>
      )}
    </ToastContext.Provider>
  );
}
