"use client";

import React from "react";
import { cn } from "@/utils/cn";

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
          <div className="flex h-px w-full flex-none flex-col items-center gap-2 bg-brand-primary" />
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
          <div className="flex h-px w-full flex-none flex-col items-center gap-2 bg-brand-primary" />
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
          <div className="flex h-px w-full flex-none flex-col items-center gap-2 bg-brand-primary" />
        </div>
      </div>
    );
  }
);

export const SignIn = SignInRoot;
