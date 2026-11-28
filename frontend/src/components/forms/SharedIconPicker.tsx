import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as Popover from "@radix-ui/react-popover";

import { TextField } from "@/components/forms/TextField";
import { usePortalContainer } from "@/contexts/PortalContainerContext";
import { cn } from "@/utils/cn";
import { getAvailableIconNames, getIconComponent } from "@/utils/iconMapping";

export function SharedIconPicker({ value, onChange, className }: {
  value: string;
  onChange: (icon: string) => void;
  className?: string;
}) {
  const portalContainer = usePortalContainer();
  const contentRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [iconSearchTerm, setIconSearchTerm] = useState("");
  const allIconNames = useMemo(() => getAvailableIconNames(), []);
  const filteredIcons = useMemo(
    () => allIconNames.filter((name) => name.toLowerCase().includes(iconSearchTerm.toLowerCase())),
    [allIconNames, iconSearchTerm],
  );
  const handleOpenChange = useCallback((nextOpen: boolean) => {
    setOpen(nextOpen);
    if (!nextOpen) setIconSearchTerm("");
  }, []);

  useEffect(() => {
    if (!open || !portalContainer) return;
    const view = portalContainer.ownerDocument.defaultView;
    function closePickerOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape" || !(event.target instanceof Node) || !contentRef.current?.contains(event.target)) return;
      event.preventDefault();
      handleOpenChange(false);
    }

    // The bundled UX dialog and this popover use separate Radix layer stacks.
    // Handle Escape inside the picker before the dialog's document listener sees it.
    view?.addEventListener("keydown", closePickerOnEscape, true);
    return () => view?.removeEventListener("keydown", closePickerOnEscape, true);
  }, [handleOpenChange, open, portalContainer]);

  return (
    <div className={cn("flex w-full flex-col gap-2", className)}>
      <span className="text-body-bold font-body-bold text-default-font">Icon</span>
      <Popover.Root open={open} onOpenChange={handleOpenChange}>
        <Popover.Trigger asChild>
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-md border border-solid border-neutral-border bg-default-background px-3 py-2 text-left hover:border-neutral-400"
            aria-label={`Icon ${value}`}
          >
            <span className="text-[20px] text-neutral-700">{getIconComponent(value)}</span>
            <span className="flex-1 text-body font-body text-default-font">{value}</span>
          </button>
        </Popover.Trigger>
        <Popover.Portal container={portalContainer}>
          <Popover.Content
            ref={contentRef}
            aria-label="Choose an icon"
            align="start"
            sideOffset={4}
            collisionPadding={8}
            className="z-[var(--z-popover)] flex max-h-[var(--radix-popover-content-available-height)] w-[var(--radix-popover-trigger-width)] flex-col rounded-md border border-solid border-neutral-border bg-default-background shadow-lg"
          >
            <div className="shrink-0 p-2">
              <TextField className="h-auto w-full">
                <TextField.Input
                  aria-label="Search icons"
                  placeholder="Search icons..."
                  value={iconSearchTerm}
                  onChange={(event) => setIconSearchTerm(event.target.value)}
                />
              </TextField>
            </div>
            <div className="min-h-0 max-h-64 overflow-y-auto">
              {filteredIcons.map((iconName) => (
                <Popover.Close asChild key={iconName}>
                  <button
                    type="button"
                    className="flex w-full items-center gap-3 px-4 py-2 text-left hover:bg-neutral-100"
                    onClick={() => onChange(iconName)}
                  >
                    <span className="text-[20px] text-neutral-700">{getIconComponent(iconName)}</span>
                    <span className="text-body font-body text-default-font">{iconName}</span>
                  </button>
                </Popover.Close>
              ))}
            </div>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    </div>
  );
}
