import React from "react";

import { cn } from "@/utils/cn";

interface ModalShellProps {
  children: React.ReactNode;
  panelClassName?: string;
  contentClassName?: string;
}

export function ModalShell({
  children,
  panelClassName,
  contentClassName,
}: ModalShellProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black bg-opacity-50 p-4">
      <div
        className={cn(
          "flex max-h-full w-full flex-col rounded-md bg-neutral-100 px-6 py-6",
          panelClassName,
        )}
      >
        <div
          className={cn(
            "flex min-h-0 w-full flex-col items-start gap-6",
            contentClassName,
          )}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
