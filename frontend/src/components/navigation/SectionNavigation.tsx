import { useMemo } from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/utils/cn";

export interface SectionNavigationItem {
  id: string;
  label: string;
  group: string;
}

export interface SectionNavigationProps {
  items: SectionNavigationItem[];
  activeSectionId: string;
  activeSectionLabel: string;
  isDarkTheme: boolean;
  onNavigate: (sectionId: string) => void;
  isCompact?: boolean;
  isOpen?: boolean;
  onToggle?: () => void;
  ariaLabel?: string;
  title?: string;
  compactEyebrow?: string;
}

export function SectionNavigation({
  items,
  activeSectionId,
  activeSectionLabel,
  isDarkTheme,
  onNavigate,
  isCompact = false,
  isOpen = true,
  onToggle,
  ariaLabel = "Page sections",
  title = "Sections",
  compactEyebrow = "Jump To Section",
}: SectionNavigationProps) {
  const groupedItems = useMemo(() => {
    const groups: Array<{ name: string; items: SectionNavigationItem[] }> = [];

    items.forEach((item) => {
      const existingGroup = groups.find((group) => group.name === item.group);
      if (existingGroup) {
        existingGroup.items.push(item);
        return;
      }

      groups.push({ name: item.group, items: [item] });
    });

    return groups;
  }, [items]);

  return (
    <nav
      aria-label={ariaLabel}
      className={cn(
        "rounded-lg border border-neutral-border bg-default-background",
        isCompact ? "w-full overflow-hidden" : "w-full p-4",
      )}
    >
      {isCompact ? (
        <>
          <button
            type="button"
            onClick={onToggle}
            className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
            aria-expanded={isOpen}
          >
            <div className="flex flex-col gap-1">
              <span className="text-caption font-caption uppercase tracking-[0.12em] text-subtext-color">
                {compactEyebrow}
              </span>
              <span className="text-body-bold font-body-bold text-default-font">
                {activeSectionLabel}
              </span>
            </div>
            <ChevronDown
              className={cn(
                "h-4 w-4 text-subtext-color transition-transform",
                isOpen && "rotate-180",
              )}
            />
          </button>
          {isOpen ? (
            <div className="border-t border-neutral-border px-3 py-3">
              <div className="flex flex-col gap-4">
                {groupedItems.map((group) => (
                  <div key={group.name} className="flex flex-col gap-1">
                    <span className="px-2 text-caption font-caption uppercase tracking-[0.08em] text-subtext-color">
                      {group.name}
                    </span>
                    {group.items.map((item) => {
                      const isActive = item.id === activeSectionId;
                      return (
                        <button
                          key={item.id}
                          type="button"
                          onClick={() => onNavigate(item.id)}
                          className={cn(
                            "flex w-full items-center rounded-md px-2 py-2 text-left text-body transition-colors",
                            isActive
                              ? isDarkTheme
                                ? "bg-brand-1000 text-brand-primary"
                                : "bg-neutral-100 text-neutral-1000"
                              : "text-subtext-color hover:bg-neutral-50 hover:text-default-font",
                          )}
                        >
                          {item.label}
                        </button>
                      );
                    })}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </>
      ) : (
        <div className="flex flex-col gap-5">
          <div className="flex flex-col gap-1 border-b border-neutral-border pb-3">
            <span className="text-caption font-caption uppercase tracking-[0.12em] text-subtext-color">
              On This Page
            </span>
            <span className="text-body-bold font-body-bold text-default-font">
              {title}
            </span>
          </div>
          {groupedItems.map((group) => (
            <div key={group.name} className="flex flex-col gap-1">
              <span className="px-2 text-caption font-caption uppercase tracking-[0.08em] text-subtext-color">
                {group.name}
              </span>
              {group.items.map((item) => {
                const isActive = item.id === activeSectionId;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => onNavigate(item.id)}
                    className={cn(
                      "flex w-full items-center rounded-md border px-3 py-2 text-left text-body transition-colors",
                      isActive
                        ? isDarkTheme
                          ? "border-brand-primary bg-brand-1000 text-brand-primary"
                          : "border-neutral-1000 bg-neutral-100 text-neutral-1000"
                        : "border-transparent text-subtext-color hover:border-neutral-border hover:bg-neutral-50 hover:text-default-font",
                    )}
                    aria-current={isActive ? "location" : undefined}
                  >
                    {item.label}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </nav>
  );
}
