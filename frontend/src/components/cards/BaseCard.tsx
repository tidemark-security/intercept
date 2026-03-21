"use client";

import React from "react";

import { useTheme } from "@/contexts/ThemeContext";

import { cn } from "@/utils/cn";
import { IconWrapper } from "@/utils/IconWrapper";

import { Cpu, Crown } from 'lucide-react';
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
      className,
      children,
      ...otherProps
    }: BaseCardRootProps,
    ref
  ) {
    const { resolvedTheme } = useTheme();
    const isDarkTheme = resolvedTheme === "dark";

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
            <IconWrapper
              className={cn(
                "text-heading-2 font-heading-2 text-default-font",
                {
                  "text-error-600": system === "error",
                  "text-warning-600": system === "warning",
                  "text-success-600": system === "success" && isDarkTheme,
                  "text-success-900": system === "success" && !isDarkTheme,
                }
              )}
            >
              {baseIcon}
            </IconWrapper>
          ) : null}
        </div>
        <div className="flex w-full flex-col items-start gap-1">
          {(line1 || line1Icon) ? (
            <div className="flex w-full items-center gap-2 overflow-hidden">
              {line1Icon ? (
                <IconWrapper
                  className={cn(
                    "text-body font-body text-subtext-color",
                    { hidden: size === "small" }
                  )}
                >
                  {line1Icon}
                </IconWrapper>
              ) : null}
              {line1 ? (
                <span
                  className={cn(
                    "line-clamp-2 break-words text-body-bold font-body-bold text-default-font",
                    {
                      "text-caption-bold font-caption-bold": size === "small",
                      "text-default-font": system === "warning",
                    }
                  )}
                >
                  {line1}
                </span>
              ) : null}
            </div>
          ) : null}
          {(line2 || line2Icon) ? (
            <div className="flex w-full items-center gap-2 overflow-hidden">
              {line2Icon ? (
                <IconWrapper
                  className={cn(
                    "text-body font-body text-subtext-color",
                    { hidden: size === "small" }
                  )}
                >
                  {line2Icon}
                </IconWrapper>
              ) : null}
              {line2 ? (
                <span className="line-clamp-2 break-words text-caption font-caption text-subtext-color">
                  {line2}
                </span>
              ) : null}
            </div>
          ) : null}
          {(line3 || line3Icon) ? (
            <div
              className={cn("flex w-full items-center gap-2 overflow-hidden", {
                hidden: size === "small",
              })}
            >
              {line3Icon ? (
                <IconWrapper className="text-body font-body text-subtext-color">
                  {line3Icon}
                </IconWrapper>
              ) : null}
              {line3 ? (
                <span className="line-clamp-1 break-words text-caption font-caption text-subtext-color">
                  {line3}
                </span>
              ) : null}
            </div>
          ) : null}
          {(line4 || line4Icon) ? (
            <div
              className={cn("flex w-full items-center gap-2 overflow-hidden", {
                hidden: size === "small",
              })}
            >
              {line4Icon ? (
                <IconWrapper className="text-body font-body text-subtext-color">
                  {line4Icon}
                </IconWrapper>
              ) : null}
              {line4 ? (
                <span className="line-clamp-1 break-words text-caption font-caption text-subtext-color">
                  {line4}
                </span>
              ) : null}
            </div>
          ) : null}
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
          <div className="flex w-full flex-col items-start gap-4">
            {children}
          </div>
        ) : null}
        <div className="mt-auto flex w-full flex-col items-start">
          {actionButtons ? (
            <div className="flex w-full flex-col items-start">
              {actionButtons}
            </div>
          ) : null}
        </div>
      </div>
    );
  }
);

export const BaseCard = BaseCardRoot;
