"use client";

import React from "react";
import { cn } from "@/utils/cn";

interface ProductCardRootProps extends React.HTMLAttributes<HTMLDivElement> {
  code?: React.ReactNode;
  logo?: string;
  description?: React.ReactNode;
  mobile?: boolean;
  tagline?: React.ReactNode;
  className?: string;
}

const ProductCardRoot = React.forwardRef<HTMLDivElement, ProductCardRootProps>(
  function ProductCardRoot(
    {
      code,
      logo,
      description,
      mobile = false,
      tagline,
      className,
      ...otherProps
    }: ProductCardRootProps,
    ref
  ) {
    return (
      <div
        className={cn(
          "group/43a80124 flex w-full cursor-pointer flex-col items-start justify-center border border-solid border-brand-primary bg-neutral-0 px-12 py-12 hover:bg-accent-2-primary",
          { "px-4 py-4": mobile },
          className
        )}
        ref={ref}
        {...otherProps}
      >
        <div className="flex items-center px-2 py-2">
          <span className="w-8 flex-none font-['Kode_Mono'] text-[30px] font-[600] leading-[36px] text-brand-primary">
            $
          </span>
          {code ? (
            <span className="grow shrink-0 basis-0 font-['Kode_Mono'] text-[30px] font-[600] leading-[36px] text-brand-primary">
              {code}
            </span>
          ) : null}
          <span className="grow shrink-0 basis-0 font-['Kode_Mono'] text-[30px] font-[600] leading-[36px] text-brand-primary animate-pulse">
            _
          </span>
        </div>
        <div className="flex flex-col items-start justify-center px-2 py-2">
          {logo ? <img className="max-h-[48px] flex-none" src={logo} /> : null}
        </div>
        <div className="flex w-full flex-col items-center gap-4 px-2 py-2">
          {tagline ? (
            <span className="w-full font-['Kode_Mono'] text-[22px] font-[400] leading-[22px] text-brand-primary">
              {tagline}
            </span>
          ) : null}
          {description ? (
            <span className="w-full font-['Kode_Mono'] text-[22px] font-[400] leading-[22px] text-brand-primary">
              {description}
            </span>
          ) : null}
        </div>
      </div>
    );
  }
);

export const ProductCard = ProductCardRoot;
