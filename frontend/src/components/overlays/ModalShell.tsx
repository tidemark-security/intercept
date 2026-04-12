import React from "react";

import { Dialog } from "@tidemark-security/ux";
import * as VisuallyHidden from "@radix-ui/react-visually-hidden";

import { cn } from "@/utils/cn";

interface ModalShellProps {
  children: React.ReactNode;
  title: string;
  description?: string;
  panelClassName?: string;
  contentClassName?: string;
  onClose?: () => void;
}

export function ModalShell({
  children,
  title,
  description,
  panelClassName,
  contentClassName,
  onClose,
}: ModalShellProps) {
  return (
    <Dialog
      open={true}
      onOpenChange={(open) => {
        if (!open) onClose?.();
      }}
      className="p-4"
    >
      <Dialog.Content
        className={cn(
          "w-full bg-neutral-100 px-6 py-6",
          panelClassName,
        )}
      >
        <VisuallyHidden.Root asChild>
          <Dialog.Title>{title}</Dialog.Title>
        </VisuallyHidden.Root>
        {description && (
          <VisuallyHidden.Root asChild>
            <Dialog.Description>{description}</Dialog.Description>
          </VisuallyHidden.Root>
        )}
        <div
          className={cn(
            "flex min-h-0 w-full flex-col items-start gap-6",
            contentClassName,
          )}
        >
          {children}
        </div>
      </Dialog.Content>
    </Dialog>
  );
}
