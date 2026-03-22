"use client";

import React from "react";
import { cn } from "@/utils/cn";
import { useTheme } from "@/contexts/ThemeContext";

interface SignInRootProps extends React.HTMLAttributes<HTMLDivElement> {
  logo?: string;
  externalSignInOptions?: React.ReactNode;
  passkeyButton?: React.ReactNode;
  emailField?: React.ReactNode;
  passwordField?: React.ReactNode;
  submitButton?: React.ReactNode;
  enableExternal?: boolean;
  className?: string;
}

const SignInRoot = React.forwardRef<HTMLDivElement, SignInRootProps>(
  function SignInRoot(
    {
      logo,
      externalSignInOptions,
      passkeyButton,
      emailField,
      passwordField,
      submitButton,
      enableExternal = false,
      className,
      ...otherProps
    }: SignInRootProps,
    ref
  ) {
    const { resolvedTheme } = useTheme();
    const isDarkTheme = resolvedTheme === "dark";

    return (
      <div
        className={cn(
          "group/c8985f7c flex w-full max-w-[448px] flex-col items-center justify-center gap-8 rounded-md px-6 py-6",
          className
        )}
        ref={ref}
        {...otherProps}
      >
        <img
          className="flex-none"
          src={logo}
        />
        <div
          className={cn(
            "hidden w-full flex-col items-center justify-center gap-4",
            { flex: enableExternal }
          )}
        >
          <hr className={cn("w-full", isDarkTheme ? "border-brand-primary" : "border-neutral-1000")} />
          <span className="w-full text-heading-2 font-heading-2 text-subtext-color">
            External sign in
          </span>
          {externalSignInOptions ? (
            <div className="flex w-full flex-col items-start justify-center gap-2">
              {externalSignInOptions}
            </div>
          ) : null}
        </div>
        <div className="flex w-full flex-col items-center justify-center gap-4">
          <hr className={cn("w-full", isDarkTheme ? "border-brand-primary" : "border-neutral-1000")} />
          <span className="w-full text-heading-2 font-heading-2 text-subtext-color">
            Local sign in
          </span>
          {emailField ? (
            <div className="flex w-full flex-col items-start justify-center gap-2">
              {emailField}
            </div>
          ) : null}
          {passkeyButton ? (
            <div className="flex w-full flex-col items-center justify-center gap-8">
              {passkeyButton}
            </div>
          ) : null}
          {passwordField ? (
            <div className="flex w-full flex-col items-start justify-center gap-2">
              {passwordField}
            </div>
          ) : null}
          {submitButton ? (
            <div className="flex w-full flex-col items-center justify-center gap-8">
              {submitButton}
            </div>
          ) : null}
          <hr className={cn("w-full", isDarkTheme ? "border-brand-primary" : "border-neutral-1000")} />
        </div>
      </div>
    );
  }
);

export const SignIn = SignInRoot;
