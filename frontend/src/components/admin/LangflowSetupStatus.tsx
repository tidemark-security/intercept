import { AlertCircle, CheckCircle } from "lucide-react";

import type { LangFlowSetupResponse } from "@/types/generated/models/LangFlowSetupResponse";
import { cn } from "@/utils/cn";

type StatusVariant = "success" | "error" | "warning";

interface LangflowSetupStatusProps {
  status: LangFlowSetupResponse;
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
  children,
}: {
  variant: StatusVariant;
  title: string;
  description?: string;
  isDarkTheme: boolean;
  children?: React.ReactNode;
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
      {children}
    </div>
  );
}

function getStepVariant(stepStatus: string): StatusVariant {
  if (stepStatus === "failed") {
    return "error";
  }
  if (stepStatus === "warning") {
    return "warning";
  }
  return "success";
}

export function LangflowSetupStatus({
  status,
  isDarkTheme,
}: LangflowSetupStatusProps) {
  const steps = status.steps ?? [];
  const warnings = status.warnings ?? [];
  const hasWarnings = warnings.length > 0;
  const nonWarningSteps = steps.filter((step) => step.status !== "warning");

  return (
    <div className="flex w-full flex-col gap-3">
      <StatusCallout
        variant={status.success ? (hasWarnings ? "warning" : "success") : "error"}
        title={
          status.success
            ? hasWarnings
              ? "Langflow setup completed with warnings"
              : "Langflow setup completed"
            : "Langflow setup failed"
        }
        description={status.message}
        isDarkTheme={isDarkTheme}
      >
        {warnings.length > 0 && (
          <ul className={cn("mt-1 list-disc pl-5 text-caption font-caption", isDarkTheme ? "text-warning-300" : "text-warning-1000")}>
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        )}
      </StatusCallout>

      {nonWarningSteps.map((step) => (
        <StatusCallout
          key={step.id}
          variant={getStepVariant(step.status)}
          title={step.label}
          description={step.message}
          isDarkTheme={isDarkTheme}
        />
      ))}
    </div>
  );
}
