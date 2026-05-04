/**
 * CopyableTimestamp - Displays a timestamp with click-to-copy functionality
 * 
 * Shows relative time by default with optional label, and copies ISO8601 timestamp to clipboard.
 * Includes visual feedback (copy icon on hover, check mark after copy).
 */

import React, { useState, useCallback, useMemo } from 'react';

import { useTheme } from '@/contexts/ThemeContext';
import { useTimezonePreference } from '@/contexts/TimezoneContext';
import { cn } from '@/utils/cn';
import { parseISO8601 } from '@/utils/dateFilters';
import { formatRelativeTime } from '@/utils/dateFormatters';
import { formatTimestampForPreference } from '@/utils/timezonePreference';

import { Check, Copy } from 'lucide-react';

export interface CopyableTimestampProps {
  /** Raw timestamp value (ISO8601 string or Date-parseable string) */
  value: string | null | undefined;
  /** Optional label to display before the timestamp (e.g., "Created", "Modified") */
  label?: string;
  /** Whether to show the full ISO8601 timestamp with relative time in brackets (default: true) */
  showFull?: boolean;
  /** Whether relative time appears inline or beneath the timestamp (default: inline) */
  relativePlacement?: 'inline' | 'below';
  /** Visual variant controlling color and icon placement (default: "accent-1-left") */
  variant?: 'accent-1-left' | 'accent-1-right' | 'default-left' | 'default-right';
  /** Additional CSS classes */
  className?: string;
}

export function CopyableTimestamp({
  value,
  label,
  showFull = true,
  relativePlacement = 'inline',
  variant = 'default-right',
  className,
}: CopyableTimestampProps) {
  const { resolvedTheme } = useTheme();
  const { timezonePreference } = useTimezonePreference();
  const isDarkTheme = resolvedTheme === 'dark';
  const [isHovered, setIsHovered] = useState(false);
  const [isCopied, setIsCopied] = useState(false);
  const isRightVariant = variant.endsWith('-right');
  const isDefaultVariant = variant.startsWith('default');

  // Format timestamps
  const { relativeTime, displayTime } = useMemo(() => {
    if (!value) {
      return { relativeTime: '', displayTime: '' };
    }
    const parsed = parseISO8601(value);

    if (!parsed) {
      return { relativeTime: '', displayTime: '' };
    }

    return {
      relativeTime: formatRelativeTime(value),
      displayTime: formatTimestampForPreference(parsed, timezonePreference),
    };
  }, [value, timezonePreference]);

  // Handle copying timestamp to clipboard
  const handleCopyTimestamp = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (displayTime) {
      navigator.clipboard.writeText(displayTime)
        .then(() => {
          setIsCopied(true);
          // Reset after 2 seconds
          setTimeout(() => setIsCopied(false), 2000);
        })
        .catch(err => {
          console.error('Failed to copy timestamp:', err);
        });
    }
  }, [displayTime]);

  if (!value || !displayTime) {
    return null;
  }

  const timestampTextClasses = isDefaultVariant
    ? 'text-default-font'
    : (isDarkTheme ? 'text-accent-1-600 hover:text-accent-1-500' : 'text-accent-1-800 hover:text-accent-1-700');

  const iconClasses = cn(
    'h-3 w-3 transition-opacity',
    timestampTextClasses,
    { 'opacity-0': !isHovered && !isCopied, 'opacity-100': isHovered || isCopied }
  );

  const timestampClasses = cn(
    'text-caption font-mono',
    timestampTextClasses
  );

  const icon = isCopied ? (
    <Check className={iconClasses} />
  ) : (
    <Copy className={iconClasses} />
  );

  if (relativePlacement === 'below') {
    return (
      <div
        className={cn(
          "flex items-start gap-1 cursor-pointer group/timestamp",
          className
        )}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        onClick={handleCopyTimestamp}
        title={`Click to copy: ${displayTime}`}
      >
        {!isRightVariant && icon}
        <div className="flex min-w-0 flex-col items-end gap-0 text-right">
          <span className="flex min-w-0 items-center gap-1">
            {label && (
              <span className="text-caption font-caption text-subtext-color">
                {label}:
              </span>
            )}
            <span className={timestampClasses}>
              {displayTime}
            </span>
          </span>
          {showFull && (
            <span className="text-caption font-caption text-subtext-color">
              {relativeTime}
            </span>
          )}
        </div>
        {isRightVariant && icon}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex items-center gap-1 cursor-pointer group/timestamp",
        className
      )}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onClick={handleCopyTimestamp}
      title={`Click to copy: ${displayTime}`}
    >
      {!isRightVariant && icon}
      {label && (
        <span className="text-caption font-caption text-subtext-color">
          {label}:
        </span>
      )}
      <span className={timestampClasses}>
        {displayTime}
      </span>
      {showFull && (
        <span className="text-caption font-caption text-subtext-color">
          ({relativeTime})
        </span>
      )}
      {isRightVariant && icon}
    </div>
  );
}

export default CopyableTimestamp;
