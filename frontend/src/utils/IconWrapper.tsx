/**
 * IconWrapper component
 * 
 * Wraps icons in a span with proper flex styling to ensure consistent sizing.
 * Lucide icons automatically inherit their size from the parent's font-size
 * via the global CSS rule in index.css (svg.lucide { width: 1em; height: 1em; }).
 * 
 * @example
 * // Icon inherits size from text-body (14px) - no size prop needed!
 * <IconWrapper className="text-body text-default-font">
 *   <SomeIcon />
 * </IconWrapper>
 * 
 * // Icon inherits size from text-heading-3 (16px)
 * <IconWrapper className="text-heading-3 text-default-font">
 *   <SomeIcon />
 * </IconWrapper>
 */
import React from "react";
import { cn } from "./cn";

export const IconWrapper = React.forwardRef<
  HTMLSpanElement,
  React.HTMLAttributes<HTMLSpanElement>
>(function IconWrapper({ className, ...otherProps }, ref) {
  return (
    <span
      ref={ref}
      className={cn(
        "inline-flex flex-none items-center",
        className
      )}
      {...otherProps}
    />
  );
});

IconWrapper.displayName = "IconWrapper";
