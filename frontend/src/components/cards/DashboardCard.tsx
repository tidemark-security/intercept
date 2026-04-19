import React from "react";
import { Link } from "@/components/navigation/Link";
import { IconWithBackground } from "@/components/misc/IconWithBackground";
import { useTheme } from "@/contexts/ThemeContext";
import { cn } from "@/utils/cn";

type PriorityLevel = "info" | "low" | "medium" | "high" | "critical" | "extreme";

interface DashboardCardProps {
  title: string;
  description: string;
  icon: React.ReactNode;
  link: string;
  /** Use larger body text for stat-style cards */
  variant?: "default" | "stat";
  /** Optional priority level to show striped background effect */
  priority?: PriorityLevel;
}

/**
 * Get the background color class for a given priority level
 */
function getPriorityGradient(priority?: PriorityLevel): string {
  switch (priority) {
    case "extreme":
      return "bg-p0/60";
    case "critical":
      return "bg-p1";
    case "high":
      return "bg-p2/60";
    case "medium":
      return "bg-p3/60";
    case "low":
      return "bg-p4/60";
    case "info":
      return "bg-p5/50";
    default:
      return "bg-transparent";
  }
}

/**
 * Reusable dashboard card component for navigation and stats.
 * Displays an icon with round background, title, description, and navigates to the specified link.
 * Optionally shows priority-based striped background.
 */
export function DashboardCard({ 
  title, 
  description, 
  icon, 
  link,
  variant = "default",
  priority
}: DashboardCardProps) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark";

  const gradientClass = getPriorityGradient(priority);
  const hasStripes = !!priority;

  return (
    <Link to={link} className="group">
      <div
        className={cn(
          "relative h-full cursor-pointer rounded-lg border border-solid bg-default-background transition-all overflow-hidden",
          isDarkTheme
            ? "border-neutral-border hover:shadow-lg hover:border-brand-primary"
            : "border-neutral-border hover:shadow-black-shadow-large hover:border-black"
        )}
      >
        {/* Priority stripes background with gradient fade */}
        {hasStripes && (
          <div
            className="absolute inset-0 z-0 pointer-events-none"
            style={{
              maskImage: "linear-gradient(-45deg, rgba(0,0,0,1) 0%, rgba(0,0,0,0.7) 3%, rgba(0,0,0,0.4) 6%, rgba(0,0,0,0.1) 20%, transparent 60%)",
              WebkitMaskImage: "linear-gradient(-45deg, rgba(0,0,0,1) 0%, rgba(0,0,0,0.7) 3%, rgba(0,0,0,0.4) 6%, rgba(0,0,0,0.1) 20%, transparent 60%)",
            }}
          >
            <div
              className={`absolute inset-0 transition-colors duration-500 ${gradientClass}`}
              style={{
                maskImage:
                  "repeating-linear-gradient(135deg, transparent, transparent 10px, black 10px, black 20px)",
                WebkitMaskImage:
                  "repeating-linear-gradient(135deg, transparent, transparent 10px, black 10px, black 20px)",
              }}
            />
          </div>
        )}
        
        {/* Content */}
        <div className="relative z-10 flex h-full flex-col items-start gap-4 p-6">
          {/* Icon with round background */}
          <IconWithBackground
            variant="brand"
            size="large"
            icon={icon}
          />
          
          {/* Content */}
          <div className="flex flex-col items-start gap-2">
            <span className="text-heading-3 font-heading-3 text-default-font">
              {title}
            </span>
            <span className={variant === "stat" 
              ? "text-heading-2 font-heading-2 text-default-font"
              : "text-body font-body text-subtext-color"
            }>
              {description}
            </span>
          </div>

          {/* Arrow indicator */}
          <div className="mt-auto flex w-full items-center justify-end">
            <span
              className={cn(
                "text-caption font-caption opacity-0 transition-opacity group-hover:opacity-100",
                isDarkTheme ? "text-brand-primary" : "text-black"
              )}
            >
              View →
            </span>
          </div>
        </div>
      </div>
    </Link>
  );
}

/**
 * Helper to determine priority level based on alert count thresholds
 * 0 alerts = no priority (no stripes)
 * 1-5 alerts = info
 * 6-15 alerts = low  
 * 16-30 alerts = medium
 * 31-50 alerts = high
 * 51-99 alerts = critical
 * 100+ alerts = extreme
 */
export function getAlertCountPriority(count: number): PriorityLevel | undefined {
  if (count === 0) return undefined;
  if (count <= 5) return "info";
  if (count <= 15) return "low";
  if (count <= 30) return "medium";
  if (count <= 50) return "high";
  if (count <= 99) return "critical";
  return "extreme";
}
