"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";

import { useTheme } from "@/contexts/ThemeContext";

import { cn } from "@/utils/cn";
import { IconWrapper } from "@/utils/IconWrapper";

import { Check, Copy, Cpu } from "lucide-react";

export type CopyTarget = "title" | "line1" | "line2" | "line3" | "line4";

function extractTextFromNode(node: React.ReactNode): string {
  if (node == null || typeof node === "boolean") {
    return "";
  }

  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }

  if (Array.isArray(node)) {
    return node.map(extractTextFromNode).join(" ");
  }

  if (React.isValidElement<{ children?: React.ReactNode }>(node)) {
    return extractTextFromNode(node.props.children);
  }

  return "";
}

function normalizeClipboardText(node: React.ReactNode): string {
  return extractTextFromNode(node).replace(/\s+/g, " ").trim();
}

interface BaseCardRootProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  title?: React.ReactNode;
  baseIcon?: React.ReactNode;
  accentIcon?: React.ReactNode;
  accentText?: React.ReactNode;
  line1?: React.ReactNode;
  line2?: React.ReactNode;
  line3?: React.ReactNode;
  line4?: React.ReactNode;
  actionButtons?: React.ReactNode;
  system?: "default" | "success" | "warning" | "error";
  characterFlags?: React.ReactNode;
  line1Icon?: React.ReactNode;
  line2Icon?: React.ReactNode;
  line3Icon?: React.ReactNode;
  line4Icon?: React.ReactNode;
  size?: "x-large" | "large" | "medium" | "small";
  enableCopyInteractions?: boolean;
  disableCopyTargets?: CopyTarget[];
  className?: string;
  children?: React.ReactNode;
}

const BaseCardRoot = React.forwardRef<HTMLDivElement, BaseCardRootProps>(
  function BaseCardRoot(
    {
      title,
      baseIcon = <Cpu />,
      accentIcon,
      accentText,
      line1,
      line2,
      line3,
      line4,
      actionButtons,
      system = "default",
      characterFlags,
      line1Icon,
      line2Icon,
      line3Icon,
      line4Icon,
      size = "large",
      enableCopyInteractions = false,
      disableCopyTargets = [],
      className,
      children,
      ...otherProps
    }: BaseCardRootProps,
    ref
  ) {
    const { resolvedTheme } = useTheme();
    const isDarkTheme = resolvedTheme === "dark";
    const [hoveredTarget, setHoveredTarget] = useState<CopyTarget | null>(null);
    const [copiedTarget, setCopiedTarget] = useState<CopyTarget | null>(null);
    const resetCopyTimeoutRef = useRef<number | null>(null);

    const titleText = normalizeClipboardText(title);
    const line1Text = normalizeClipboardText(line1);
    const line2Text = normalizeClipboardText(line2);
    const line3Text = normalizeClipboardText(line3);
    const line4Text = normalizeClipboardText(line4);

    const isCopyEnabled = useCallback(
      (target: CopyTarget, text: string) =>
        enableCopyInteractions && Boolean(text) && !disableCopyTargets.includes(target),
      [disableCopyTargets, enableCopyInteractions]
    );

    useEffect(() => {
      return () => {
        if (resetCopyTimeoutRef.current !== null) {
          window.clearTimeout(resetCopyTimeoutRef.current);
        }
      };
    }, []);

    const scheduleCopyReset = useCallback(() => {
      if (resetCopyTimeoutRef.current !== null) {
        window.clearTimeout(resetCopyTimeoutRef.current);
      }

      resetCopyTimeoutRef.current = window.setTimeout(() => {
        setCopiedTarget(null);
      }, 2000);
    }, []);

    const handleCopy = useCallback(
      (target: CopyTarget, text: string) =>
        (event: React.MouseEvent) => {
          event.preventDefault();
          event.stopPropagation();

          if (!enableCopyInteractions || !text || !navigator.clipboard?.writeText) {
            return;
          }

          navigator.clipboard.writeText(text)
            .then(() => {
              setCopiedTarget(target);
              scheduleCopyReset();
            })
            .catch(error => {
              console.error("Failed to copy card text:", error);
            });
        },
      [enableCopyInteractions, scheduleCopyReset]
    );

    const renderInteractiveIcon = useCallback(
      (
        target: CopyTarget,
        defaultIcon: React.ReactNode,
        className: string,
        hasText: boolean,
        reserveSpace = false
      ) => {
        const copyEnabled = isCopyEnabled(target, hasText ? "content" : "");

        if (!defaultIcon && !copyEnabled) {
          return null;
        }

        const isHovered = hoveredTarget === target;
        const isCopied = copiedTarget === target;
        const iconNode = copyEnabled && isCopied ? <Check /> : copyEnabled && isHovered ? <Copy /> : defaultIcon ?? <Copy />;

        return (
          <IconWrapper
            className={cn(
              className,
              reserveSpace && "min-w-[1em] justify-center",
              copyEnabled && hasText && !defaultIcon && !isHovered && !isCopied && "opacity-0"
            )}
            aria-hidden="true"
          >
            {iconNode}
          </IconWrapper>
        );
      },
      [copiedTarget, hoveredTarget, isCopyEnabled]
    );

    const renderCopyableLine = useCallback(
      (
        target: Extract<CopyTarget, "line1" | "line2" | "line3" | "line4">,
        lineValue: React.ReactNode,
        lineIcon: React.ReactNode,
        lineText: string,
        rowClassName: string,
        iconClassName: string,
        textClassName: string,
        hideOnSmall = false
      ) => {
        if (!lineValue && !lineIcon) {
          return null;
        }

        const interactive = isCopyEnabled(target, lineText);

        return (
          <div
            className={cn(rowClassName, interactive && "cursor-pointer")}
            onMouseEnter={interactive ? () => setHoveredTarget(target) : undefined}
            onMouseLeave={interactive ? () => setHoveredTarget(current => (current === target ? null : current)) : undefined}
            onClick={interactive ? handleCopy(target, lineText) : undefined}
            title={interactive ? `Click to copy: ${lineText}` : undefined}
          >
            {(lineIcon || interactive) ? renderInteractiveIcon(
              target,
              lineIcon,
              cn(iconClassName, hideOnSmall && "hidden"),
              Boolean(lineText),
              interactive
            ) : null}
            {lineValue ? (
              <span className={textClassName}>
                {lineValue}
              </span>
            ) : null}
          </div>
        );
      },
      [handleCopy, isCopyEnabled, renderInteractiveIcon]
    );

    return (
      <div
        className={cn(
          "group/3e384f9c flex h-auto w-full flex-col items-start gap-3 rounded-md border border-solid border-neutral-border px-4 py-3",
          isDarkTheme ? "bg-neutral-0" : "bg-neutral-50",
          {
            "min-h-[100px] w-36 flex-nowrap gap-1 px-2 py-2": size === "small",
            "min-h-[110px] w-full max-w-[320px] flex-nowrap gap-2":
              size === "medium",
            "min-h-[130px] w-full max-w-[448px] gap-3 px-4 py-3":
              size === "large",
            "min-h-[130px] w-full max-w-[1024px] gap-3 px-4 py-3":
              size === "x-large",
            "border border-solid border-error-600": system === "error",
            "border border-solid border-warning-600": system === "warning",
            "border border-solid border-success-600": system === "success",
          },
          className
        )}
        ref={ref}
        {...otherProps}
      >
        <div className={cn("flex w-full items-center gap-2", {
          "gap-1": size === "small"
        })}>
          <div className="flex grow shrink-0 basis-0 items-center gap-2">
            {title ? (
              <span
                className={cn(
                  "line-clamp-1 grow shrink-0 basis-0 break-words text-heading-3 font-heading-3 text-default-font",
                  { "text-default-font": system === "warning" }
                )}
                onMouseEnter={isCopyEnabled("title", titleText) ? () => setHoveredTarget("title") : undefined}
                onMouseLeave={isCopyEnabled("title", titleText) ? () => setHoveredTarget(current => (current === "title" ? null : current)) : undefined}
                onClick={isCopyEnabled("title", titleText) ? handleCopy("title", titleText) : undefined}
                title={isCopyEnabled("title", titleText) ? `Click to copy: ${titleText}` : undefined}
              >
                {title}
              </span>
            ) : null}
          </div>
          {accentText ? (
            <span
              className={cn(
                "hidden text-caption font-caption text-default-font",
                {
                  "inline text-error-600": system === "error" && size !== "small",
                  "inline text-warning-600": system === "warning" && size !== "small",
                  "inline text-success-600": system === "success" && size !== "small" && isDarkTheme,
                  "inline text-success-900": system === "success" && size !== "small" && !isDarkTheme,
                }
              )}
            >
              {accentText}
            </span>
          ) : null}
          {accentIcon ? (
            <IconWrapper
              className={cn(
                "hidden text-heading-2 font-heading-2 text-default-font",
                {
                  "inline-flex text-error-600": system === "error",
                  "inline-flex text-warning-600": system === "warning",
                  "inline-flex text-success-600": system === "success" && isDarkTheme,
                  "inline-flex text-success-900": system === "success" && !isDarkTheme,
                }
              )}
            >
              {accentIcon}
            </IconWrapper>
          ) : null}
          {baseIcon ? (
            renderInteractiveIcon(
              "title",
              baseIcon,
              cn(
                "text-heading-2 font-heading-2 text-default-font",
                {
                  "text-error-600": system === "error",
                  "text-warning-600": system === "warning",
                  "text-success-600": system === "success" && isDarkTheme,
                  "text-success-900": system === "success" && !isDarkTheme,
                }
              ),
              Boolean(titleText),
              isCopyEnabled("title", titleText)
            )
          ) : null}
        </div>
        <div className="flex w-full flex-col items-start gap-1">
          {renderCopyableLine(
            "line1",
            line1,
            line1Icon,
            line1Text,
            "flex w-full items-center gap-2 overflow-hidden",
            cn("text-body font-body text-subtext-color", { hidden: size === "small" }),
            cn(
              "line-clamp-2 break-words text-body-bold font-body-bold text-default-font",
              {
                "text-caption-bold font-caption-bold": size === "small",
                "text-default-font": system === "warning",
              }
            ),
            size === "small"
          )}
          {renderCopyableLine(
            "line2",
            line2,
            line2Icon,
            line2Text,
            "flex w-full items-center gap-2 overflow-hidden",
            cn("text-body font-body text-subtext-color", { hidden: size === "small" }),
            "line-clamp-2 break-words text-caption font-caption text-subtext-color",
            size === "small"
          )}
          {renderCopyableLine(
            "line3",
            line3,
            line3Icon,
            line3Text,
            cn("flex w-full items-center gap-2 overflow-hidden", {
              hidden: size === "small",
            }),
            "text-body font-body text-subtext-color",
            "line-clamp-1 break-words text-caption font-caption text-subtext-color"
          )}
          {renderCopyableLine(
            "line4",
            line4,
            line4Icon,
            line4Text,
            cn("flex w-full items-center gap-2 overflow-hidden", {
              hidden: size === "small",
            }),
            "text-body font-body text-subtext-color",
            "line-clamp-1 break-words text-caption font-caption text-subtext-color"
          )}
        </div>
        {characterFlags ? (
          <div
            className={cn(
              "flex flex-col items-start gap-4",
              { hidden: size === "small" }
            )}
          >
            {characterFlags}
          </div>
        ) : null}
        {children ? (
          <div className="flex w-full flex-1 flex-col items-start gap-4">
            {children}
          </div>
        ) : null}
        {actionButtons ? (
          <div className="mt-auto flex w-full flex-col items-start">
            <div className="flex w-full flex-col items-start">
              {actionButtons}
            </div>
          </div>
        ) : null}
      </div>
    );
  }
);

export const BaseCard = BaseCardRoot;
