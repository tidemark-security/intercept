"use client";

import React from "react";
import {
  BookOpenCheck,
  BugOff,
  ClipboardCheck,
  RotateCcw,
  SearchCheck,
  ShieldCheck,
} from "lucide-react";

import type { PICERLStage } from "@/types/caseTemplates";
import { cn } from "@/utils/cn";

export type PicerlStageValue =
  | PICERLStage
  | "PREPARATION"
  | "IDENTIFICATION"
  | "CONTAINMENT"
  | "ERADICATION"
  | "RECOVERY"
  | "LESSONS_LEARNED";

export interface PicerlStageProps extends React.HTMLAttributes<HTMLDivElement> {
  stage?: PicerlStageValue | string | null;
  size?: "small" | "mini" | "maxi";
  className?: string;
}

export type PicerlStageIcon = React.ComponentType<{ className?: string }>;

export const PICERL_STAGE_LABEL_CANDIDATES: Record<PICERLStage, string[]> = {
  Preparation: ["0. Preparation", "0. Prep", "0. P", "P"],
  Identification: ["1. Identification", "1. Ident", "1. I", "I"],
  Containment: ["2. Containment", "2. Contain", "2. C", "C"],
  Eradication: ["3. Eradication", "3. Erad", "3. E", "E"],
  Recovery: ["4. Recovery", "4. Recover", "4. R", "R"],
  "Lessons Learned": ["5. Lessons Learned", "5. Lessons", "5. L", "L"],
};

export const PICERL_STAGE_ICONS: Record<PICERLStage, PicerlStageIcon> = {
  Preparation: ClipboardCheck,
  Identification: SearchCheck,
  Containment: ShieldCheck,
  Eradication: BugOff,
  Recovery: RotateCcw,
  "Lessons Learned": BookOpenCheck,
};

export function normalizePicerlStage(stage: PicerlStageProps["stage"]): PICERLStage | null {
  switch (stage) {
    case "Preparation":
    case "PREPARATION":
      return "Preparation";
    case "Identification":
    case "IDENTIFICATION":
      return "Identification";
    case "Containment":
    case "CONTAINMENT":
      return "Containment";
    case "Eradication":
    case "ERADICATION":
      return "Eradication";
    case "Recovery":
    case "RECOVERY":
      return "Recovery";
    case "Lessons Learned":
    case "LESSONS_LEARNED":
      return "Lessons Learned";
    default:
      return null;
  }
}

export function getPicerlStageLabels(stage: PICERLStage): string[] {
  return PICERL_STAGE_LABEL_CANDIDATES[stage];
}

export function getPicerlStageIcon(stage: PICERLStage): PicerlStageIcon {
  return PICERL_STAGE_ICONS[stage];
}

const PicerlStageRoot = React.forwardRef<HTMLDivElement, PicerlStageProps>(function PicerlStageRoot(
  { stage, size = "small", className, ...otherProps },
  ref,
) {
  const rootRef = React.useRef<HTMLDivElement | null>(null);
  const labelRef = React.useRef<HTMLSpanElement | null>(null);
  const measurementRefs = React.useRef<Array<HTMLSpanElement | null>>([]);
  const normalizedStage = normalizePicerlStage(stage);
  const labels = normalizedStage ? getPicerlStageLabels(normalizedStage) : [String(stage || "N/A")];
  const Icon = normalizedStage ? getPicerlStageIcon(normalizedStage) : getPicerlStageIcon("Lessons Learned");
  const [visibleLabel, setVisibleLabel] = React.useState(() => labels[0]);

  const setRootRefs = React.useCallback(
    (node: HTMLDivElement | null) => {
      rootRef.current = node;
      if (typeof ref === "function") {
        ref(node);
      } else if (ref) {
        ref.current = node;
      }
    },
    [ref],
  );

  React.useLayoutEffect(() => {
    if (size === "mini") {
      setVisibleLabel(labels[labels.length - 1]);
      return;
    }

    const root = rootRef.current;
    const labelElement = labelRef.current;
    if (!root || !labelElement) {
      return;
    }

    const updateLabelMode = () => {
      const availableWidth = labelElement.getBoundingClientRect().width;
      const nextLabel =
        labels.find((_, index) => {
          const measurementElement = measurementRefs.current[index];
          return measurementElement
            ? measurementElement.getBoundingClientRect().width <= availableWidth + 0.5
            : false;
        }) ?? labels[labels.length - 1];

      setVisibleLabel(nextLabel);
    };

    updateLabelMode();

    if (typeof ResizeObserver === "undefined") {
      return;
    }

    const resizeObserver = new ResizeObserver(updateLabelMode);
    resizeObserver.observe(root);
    resizeObserver.observe(labelElement);

    return () => {
      resizeObserver.disconnect();
    };
  }, [labels, size]);

  return (
    <div
      className={cn(
        "flex h-6 min-w-0 max-w-full items-center justify-center gap-1 overflow-hidden rounded-md border border-solid border-neutral-border bg-neutral-50 px-2",
        {
          "h-9 min-w-44": size === "maxi",
          "h-6 w-12": size === "mini",
        },
        className,
      )}
      ref={setRootRefs}
      {...otherProps}
    >
      <Icon className={cn("text-body font-body text-neutral-700", { "text-heading-2 font-heading-2": size === "maxi" })} />
      <span
        ref={labelRef}
        className={cn(
          "relative min-w-0 grow shrink basis-0 whitespace-nowrap text-center text-caption font-caption text-neutral-700",
          {
            "text-heading-2 font-heading-2": size === "maxi",
            "grow-0 shrink-0 basis-auto": size === "mini",
          },
        )}
      >
        {labels.map((measurementLabel, index) => (
          <span
            key={`${measurementLabel}-${index}`}
            ref={(node) => {
              measurementRefs.current[index] = node;
            }}
            aria-hidden="true"
            className="pointer-events-none invisible absolute left-0 top-0 whitespace-nowrap"
          >
            {measurementLabel}
          </span>
        ))}
        {visibleLabel}
      </span>
    </div>
  );
});

export const PicerlStage = PicerlStageRoot;
