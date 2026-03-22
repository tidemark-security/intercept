"use client";

import React from "react";

import { cn } from "@/utils/cn";

import { Github } from 'lucide-react';
import TMSLogo from "@/assets/TMS-logo-green.svg";
interface FooterRootProps extends React.HTMLAttributes<HTMLDivElement> {
  className?: string;
}

const FooterRoot = React.forwardRef<HTMLDivElement, FooterRootProps>(
  function FooterRoot({ className, ...otherProps }: FooterRootProps, ref) {
    return (
      <div
        className={cn(
          "flex w-full items-center justify-center overflow-hidden border-t border-solid border-neutral-100 bg-default-background",
          className
        )}
        ref={ref}
        {...otherProps}
      >
        <div className="flex max-w-[1024px] grow shrink-0 basis-0 items-center justify-between self-stretch">
          <div className="flex max-h-[224px] grow shrink-0 basis-0 flex-col items-center self-stretch px-2 py-2">
            <img
              className="h-112 w-full flex-none object-cover"
              src={TMSLogo}
            />
          </div>
          <div className="flex flex-col flex-wrap items-start justify-between self-stretch px-12 py-12">
            <span className="w-full font-['Saira'] text-[14px] font-[500] leading-[20px] text-default-font -tracking-[0.01em]">
              Tidemark Security
            </span>
            <div className="flex h-6 w-full flex-none flex-col flex-wrap items-center justify-center">
              <div className="flex h-px w-full flex-none flex-col items-center gap-2 bg-neutral-border" />
            </div>
            <div className="flex w-full grow shrink-0 basis-0 flex-wrap items-start justify-end gap-4">
              <div className="flex min-w-[144px] grow shrink-0 basis-0 flex-col items-start gap-4">
                <span className="w-full font-['Saira'] text-[14px] font-[500] leading-[20px] text-default-font -tracking-[0.01em]">
                  Products
                </span>
                <span className="font-['Saira'] text-[14px] font-[400] leading-[20px] text-subtext-color -tracking-[0.01em]">
                  Intercept
                </span>
                <span className="font-['Saira'] text-[14px] font-[400] leading-[20px] text-subtext-color -tracking-[0.01em]">
                  Hunt
                </span>
                <span className="font-['Saira'] text-[14px] font-[400] leading-[20px] text-subtext-color -tracking-[0.01em]">
                  Comply
                </span>
              </div>
              <div className="flex min-w-[144px] grow shrink-0 basis-0 flex-col items-start gap-4">
                <span className="w-full font-['Saira'] text-[14px] font-[500] leading-[20px] text-default-font -tracking-[0.01em]">
                  Company
                </span>
                <span className="font-['Saira'] text-[14px] font-[400] leading-[20px] text-subtext-color -tracking-[0.01em]">
                  Pricing
                </span>
                <span className="font-['Saira'] text-[14px] font-[400] leading-[20px] text-subtext-color -tracking-[0.01em]">
                  About
                </span>
              </div>
              <div className="flex min-w-[144px] grow shrink-0 basis-0 flex-col items-start gap-4">
                <span className="w-full font-['Saira'] text-[14px] font-[500] leading-[20px] text-default-font -tracking-[0.01em]">
                  Resources
                </span>
                <span className="font-['Saira'] text-[14px] font-[400] leading-[20px] text-subtext-color -tracking-[0.01em]">
                  Documentation
                </span>
                <span className="font-['Saira'] text-[14px] font-[400] leading-[20px] text-subtext-color -tracking-[0.01em]">
                  Support
                </span>
                <div className="flex items-center gap-2">
                  <span className="font-['Saira'] text-[14px] font-[400] leading-[20px] text-subtext-color -tracking-[0.01em]">
                    Github
                  </span>
                  <Github className="text-body font-body text-default-font" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }
);

export const Footer = FooterRoot;
