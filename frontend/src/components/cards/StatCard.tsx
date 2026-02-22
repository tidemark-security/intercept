
import React from "react";
import { IconWithBackground } from "@/components/misc/IconWithBackground";
import { Badge } from "@/components/data-display/Badge";

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  subtext?: string;
  badge?: {
    text: string;
    variant?: "neutral" | "brand" | "error" | "warning" | "success";
  };
  onClick?: () => void;
}

/**
 * Reusable stat card component for dashboard.
 * Displays a statistic with icon, label, value, and optional badge.
 */
export function StatCard({ 
  icon, 
  label, 
  value, 
  subtext, 
  badge,
  onClick 
}: StatCardProps) {
  const content = (
    <div className="flex min-w-[240px] grow shrink-0 basis-0 flex-col items-start gap-6 rounded-md border border-solid border-neutral-border bg-default-background px-8 py-8">
      <div className="flex w-full items-center gap-4">
        <IconWithBackground
          variant="brand"
          size="medium"
          icon={icon}
        />
        <div className="flex grow shrink-0 basis-0 flex-col items-start gap-1">
          <span className="text-body font-body text-subtext-color">
            {label}
          </span>
          <span className="text-heading-1 font-heading-1 text-default-font">
            {value}
          </span>
        </div>
      </div>
      {(subtext || badge) && (
        <div className="flex w-full items-center justify-between">
          {subtext && (
            <span className="text-caption font-caption text-subtext-color">
              {subtext}
            </span>
          )}
          {badge && (
            <Badge variant={badge.variant || "neutral"}>
              {badge.text}
            </Badge>
          )}
        </div>
      )}
    </div>
  );

  if (onClick) {
    return (
      <button 
        onClick={onClick}
        className="text-left transition-all hover:opacity-80 cursor-pointer"
      >
        {content}
      </button>
    );
  }

  return content;
}
