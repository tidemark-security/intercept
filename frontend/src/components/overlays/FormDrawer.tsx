import React from "react";
import { X } from "lucide-react";

import { IconButton } from "@/components/buttons/IconButton";
import { Drawer } from "@/components/overlays/Drawer";
import { cn } from "@/utils/cn";

export interface FormDrawerProps {
  open: boolean;
  title: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  widthClassName?: string;
  contentClassName?: string;
  bodyClassName?: string;
  closeLabel?: string;
  onOpenChange: (open: boolean) => void;
}

export function FormDrawer({
  open,
  title,
  description,
  children,
  footer,
  widthClassName,
  contentClassName,
  bodyClassName,
  closeLabel = "Close drawer",
  onOpenChange,
}: FormDrawerProps) {
  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <Drawer.Content
        className={cn(
          "w-[576px] max-w-full p-0 mobile:w-full",
          widthClassName,
        )}
      >
        <div
          className={cn(
            "flex h-full w-full flex-col items-center gap-6 bg-page-background p-4",
            contentClassName,
          )}
        >
          <div className="flex w-full items-center gap-2">
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <Drawer.Title className="text-heading-3 font-heading-3 text-neutral-800">
                {title}
              </Drawer.Title>
              {description ? (
                <Drawer.Description className="text-caption font-caption text-subtext-color">
                  {description}
                </Drawer.Description>
              ) : null}
            </div>
            <IconButton
              className="ml-auto"
              icon={<X />}
              aria-label={closeLabel}
              onClick={() => onOpenChange(false)}
            />
          </div>

          <div
            className={cn(
              "flex min-h-0 w-full grow flex-col items-start gap-6 overflow-y-auto border border-solid border-neutral-border bg-default-background p-4",
              bodyClassName,
            )}
          >
            {children}
          </div>

          {footer ? (
            <div className="flex w-full shrink-0 flex-col items-center gap-2">
              {footer}
            </div>
          ) : null}
        </div>
      </Drawer.Content>
    </Drawer>
  );
}
