import { AlertCircle, CheckCircle } from "lucide-react";

import type { TestConnectionResponse } from "@/types/generated/models/TestConnectionResponse";
import { cn } from "@/utils/cn";

type StatusVariant = "success" | "error" | "warning";

interface LangflowConnectionStatusProps {
  status: TestConnectionResponse;
  isDarkTheme: boolean;
}

function getStatusVariantVisuals(variant: StatusVariant, isDarkTheme: boolean) {
  if (variant === "success") {
    return {
      icon: CheckCircle,
      containerClass: isDarkTheme
        ? "border-success-500 bg-success-1000"
        : "border-success-600 bg-success-50",
      iconClass: isDarkTheme ? "text-success-500" : "text-success-800",
      titleClass: isDarkTheme ? "text-success-500" : "text-success-900",
      descriptionClass: isDarkTheme ? "text-success-400" : "text-success-900",
    };
  }

  if (variant === "error") {
    return {
      icon: AlertCircle,
      containerClass: isDarkTheme
        ? "border-error-500 bg-error-1000"
        : "border-error-200 bg-error-50",
      iconClass: isDarkTheme ? "text-error-500" : "text-error-800",
      titleClass: isDarkTheme ? "text-error-500" : "text-error-900",
      descriptionClass: isDarkTheme ? "text-error-400" : "text-error-800",
    };
  }

  return {
    icon: AlertCircle,
    containerClass: isDarkTheme
      ? "border-warning-500 bg-warning-1000"
      : "border-warning-200 bg-warning-50",
    iconClass: isDarkTheme ? "text-warning-500" : "text-warning-800",
    titleClass: isDarkTheme ? "text-warning-500" : "text-warning-900",
    descriptionClass: isDarkTheme ? "text-warning-400" : "text-warning-800",
  };
}

function StatusCallout({
  variant,
  title,
  description,
  isDarkTheme,
}: {
  variant: StatusVariant;
  title: string;
  description?: string;
  isDarkTheme: boolean;
}) {
  const {
    icon: Icon,
    containerClass,
    iconClass,
    titleClass,
    descriptionClass,
  } = getStatusVariantVisuals(variant, isDarkTheme);

  return (
    <div
      className={cn(
        "flex flex-col gap-1 rounded-md border p-3",
        containerClass,
      )}
    >
      <div className="flex items-center gap-2">
        <Icon className={cn("h-4 w-4", iconClass)} />
        <span className={cn("text-body-bold font-body-bold", titleClass)}>
          {title}
        </span>
      </div>
      {description && (
        <p className={cn("text-caption font-caption", descriptionClass)}>
          {description}
        </p>
      )}
    </div>
  );
}

export function LangflowConnectionStatus({
  status,
  isDarkTheme,
}: LangflowConnectionStatusProps) {
  const checks = status.checks ?? [];
  const passedChecks = checks.filter((check) => check.success).length;
  const hasPartialSuccess = !status.success && passedChecks > 0;

  return (
    <div className="flex flex-col gap-3">
      <StatusCallout
        variant={status.success ? "success" : hasPartialSuccess ? "warning" : "error"}
        title={
          status.success
            ? "LangFlow environment checks passed"
            : hasPartialSuccess
              ? "LangFlow environment checks partially passed"
              : "LangFlow environment checks failed"
        }
        description={status.message}
        isDarkTheme={isDarkTheme}
      />
      {checks.map((check) => (
        <StatusCallout
          key={check.id}
          variant={check.success ? "success" : "error"}
          title={check.label}
          description={check.message}
          isDarkTheme={isDarkTheme}
        />
      ))}
    </div>
  );
}