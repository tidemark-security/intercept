import React from "react";

import { Select } from "@/components/forms/Select";
import { useTheme } from "@/contexts/ThemeContext";
import { cn } from "@/utils/cn";
import type { Priority } from "@/types/generated/models/Priority";

import { BellRing, ChevronDown, ChevronUp, ChevronsDown, ChevronsUp, Info } from 'lucide-react';
// Priority options with uppercase values matching backend enum
const PRIORITY_OPTIONS: {
  value: Priority;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}[] = [
  { value: "INFO", label: "Info", icon: Info },
  { value: "LOW", label: "Low", icon: ChevronsDown },
  { value: "MEDIUM", label: "Medium", icon: ChevronDown },
  { value: "HIGH", label: "High", icon: ChevronUp },
  { value: "CRITICAL", label: "Critical", icon: ChevronsUp },
  { value: "EXTREME", label: "Extreme", icon: BellRing },
];

export interface PrioritySelectorProps {
  value: Priority;
  onChange: (value: Priority) => void;
  label?: string;
  className?: string;
  disabled?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function PrioritySelector({
  value,
  onChange,
  label = "Priority",
  className,
  disabled = false,
  open,
  onOpenChange,
}: PrioritySelectorProps) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark";

  return (
    <Select
      className={className}
      label={label}
      variant="outline"
      value={value}
      onValueChange={(val) => onChange(val as Priority)}
      open={open}
      onOpenChange={onOpenChange}
      disabled={disabled}
    >
      {PRIORITY_OPTIONS.map((option) => (
        <Select.Item key={option.value} value={option.value}>
          <div className="flex items-center gap-2">
            <option.icon className={cn(isDarkTheme ? "text-default-font" : "text-neutral-1000")} />
            <span>{option.label}</span>
          </div>
        </Select.Item>
      ))}
    </Select>
  );
}
