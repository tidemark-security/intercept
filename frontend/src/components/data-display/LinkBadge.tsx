/**
 * LinkBadge component for rendering links as styled badge-links.
 * 
 * This is the base component used by ReferenceBadge and markdown renderers
 * for consistent link styling across the application.
 */

import React from 'react';
import { ExternalLink, Link } from 'lucide-react';
import { cn } from '@/utils/cn';
import { useTheme } from '@/contexts/ThemeContext';

export interface LinkBadgeProps {
  /** The link href */
  href: string;
  /** The display text */
  children: React.ReactNode;
  /** Whether the link is valid/active */
  isValid?: boolean;
  /** Tooltip text */
  title?: string;
  /** Additional class names */
  className?: string;
}

export function LinkBadge({ 
  href,
  children,
  isValid = true,
  title,
  className,
}: LinkBadgeProps) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';

  // Infer external vs internal from URL pattern
  const isExternal = href.startsWith('http');
  const Icon = isExternal ? ExternalLink : Link;
  
  // Base styles for the badge
  const baseStyles = cn(
    "relative z-0 inline-flex items-center align-middle gap-1 px-1 py-0 text-xs font-medium leading-none",
    "before:content-[''] before:absolute before:-z-10 before:-inset-y-1 before:inset-x-0 before:rounded",
    'transition-colors no-underline',
  );
  
  // Valid link styles
  const validStyles = cn(
    'text-brand-500 mx-0.5',
    isDarkTheme ? 'before:bg-neutral-200' : 'before:bg-neutral-600',
    'hover:before:bg-brand-1000',
    'cursor-pointer',
  );
  
  // Invalid link styles
  const invalidStyles = cn(
    'before:bg-neutral-100 text-neutral-400',
    'cursor-not-allowed',
  );
  
  if (!isValid) {
    return (
      <span
        className={cn(baseStyles, invalidStyles, className)}
        title={title || "Link not available"}
      >
        <Icon className="h-3 w-3 flex-shrink-0" />
        <span className="font-mono leading-none">{children}</span>
      </span>
    );
  }
  
  return (
    <a
      href={href}
      className={cn(baseStyles, validStyles, className)}
      title={title}
    >
      <Icon className="h-3 w-3 flex-shrink-0" />
      <span className="font-mono leading-none">{children}</span>
    </a>
  );
}
