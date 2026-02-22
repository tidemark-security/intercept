import React from "react";

import { Select } from "@/components/forms/Select";
import type { Priority } from "@/types/generated/models/Priority";

import { BellRing, ChevronDown, ChevronUp, ChevronsDown, ChevronsUp, Info } from 'lucide-react';
// Priority options with uppercase values matching backend enum
const PRIORITY_OPTIONS: { value: Priority; label: string; icon: React.ReactNode }[] = [
  { value: "INFO", label: "Info", icon: <Info className="text-neutral-400" /> },
  { value: "LOW", label: "Low", icon: <ChevronsDown className="text-neutral-400" /> },
  { value: "MEDIUM", label: "Medium", icon: <ChevronDown className="text-white" /> },
  { value: "HIGH", label: "High", icon: <ChevronUp className="text-white" /> },
  { value: "CRITICAL", label: "Critical", icon: <ChevronsUp className="text-white" /> },
  { value: "EXTREME", label: "Extreme", icon: <BellRing className="text-white" /> },
];

export interface PrioritySelectorProps {
  value: Priority;
  onChange: (value: Priority) => void;
  label?: string;
  className?: string;
  disabled?: boolean;
}

export function PrioritySelector({
  value,
  onChange,
  label = "Priority",
  className,
  disabled = false,
}: PrioritySelectorProps) {
  return (
    <Select
      className={className}
      label={label}
      variant="outline"
      value={value}
      onValueChange={(val) => onChange(val as Priority)}
      disabled={disabled}
    >
      {PRIORITY_OPTIONS.map((option) => (
        <Select.Item key={option.value} value={option.value}>
          <div className="flex items-center gap-2">
            {option.icon}
            <span>{option.label}</span>
          </div>
        </Select.Item>
      ))}
    </Select>
  );
}
