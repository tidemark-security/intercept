"use client";

import React from "react";
import { cn } from "@/utils/cn";

interface OAuthSocialButtonRootProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children?: React.ReactNode;
  logo?: string;
  disabled?: boolean;
  onClick?: (event: React.MouseEvent<HTMLButtonElement>) => void;
  className?: string;
}

const OAuthSocialButtonRoot = React.forwardRef<
  HTMLButtonElement,
  OAuthSocialButtonRootProps
>(function OAuthSocialButtonRoot(
  {
    children,
    logo,
    disabled = false,
    className,
    type = "button",
    ...otherProps
  }: OAuthSocialButtonRootProps,
  ref
) {
  return (
    <button
      className={cn(
        "group/f1948f75 flex h-10 cursor-pointer items-center justify-center gap-2 rounded-md border border-solid border-neutral-border bg-default-background px-4 hover:bg-neutral-50 disabled:cursor-default disabled:bg-black hover:disabled:cursor-default hover:disabled:bg-black active:disabled:cursor-default active:disabled:bg-black",
        className
      )}
      ref={ref}
      type={type}
      disabled={disabled}
      {...otherProps}
    >
      {logo ? (
        <img className="h-5 w-5 flex-none object-cover" src={logo} />
      ) : null}
      {children ? (
        <span className="text-body-bold font-body-bold text-neutral-700 group-disabled/f1948f75:text-neutral-400">
          {children}
        </span>
      ) : null}
    </button>
  );
});

export const OAuthSocialButton = OAuthSocialButtonRoot;
