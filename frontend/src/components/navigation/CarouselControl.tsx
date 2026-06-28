import React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { IconButton } from "@/components/buttons/IconButton";
import { cn } from "@/utils/cn";

export interface CarouselControlProps {
  count: number;
  index: number;
  onPrevious: () => void;
  onNext: () => void;
  onSelect?: (index: number) => void;
  itemLabel?: string;
  size?: "small" | "medium" | "large";
  className?: string;
}

export function CarouselControl({
  count,
  index,
  onPrevious,
  onNext,
  onSelect,
  itemLabel = "item",
  size = "small",
  className,
}: CarouselControlProps) {
  if (count <= 1) return null;

  return (
    <div className={cn("flex items-center justify-center gap-2", className)}>
      <IconButton
        aria-label={`Previous ${itemLabel}`}
        icon={<ChevronLeft />}
        size={size}
        variant="neutral-tertiary"
        onClick={onPrevious}
      />
      <div className="flex items-center gap-1">
        {Array.from({ length: count }, (_, dotIndex) => (
          <button
            key={dotIndex}
            type="button"
            aria-label={`Show ${itemLabel} ${dotIndex + 1}`}
            aria-current={dotIndex === index ? "true" : undefined}
            className={cn(
              "h-1.5 w-1.5 border border-solid border-neutral-border",
              dotIndex === index ? "bg-brand-primary" : "bg-transparent",
            )}
            onClick={() => onSelect?.(dotIndex)}
          />
        ))}
      </div>
      <IconButton
        aria-label={`Next ${itemLabel}`}
        icon={<ChevronRight />}
        size={size}
        variant="neutral-tertiary"
        onClick={onNext}
      />
    </div>
  );
}
