import React, { useCallback, useState } from 'react';

import { cn } from '@/utils/cn';

import { Check, Copy } from 'lucide-react';

export function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

export function getString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

export function getNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

export function getBoolean(value: unknown): boolean | undefined {
  return typeof value === 'boolean' ? value : undefined;
}

export function isTrue(value: unknown): boolean {
  return value === true;
}

export function EnrichmentBlockSection({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex w-full flex-col gap-3 rounded-md border border-neutral-border bg-neutral-100 p-3">
      <div className="flex items-center gap-2">
        <span className="text-subtext-color">{icon}</span>
        <span className="text-caption-bold font-caption-bold text-default-font">{title}</span>
      </div>
      {children}
    </div>
  );
}

export function EnrichmentInfoRow({
  icon,
  label,
  value,
  secondary,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  secondary?: string;
}) {
  const [isRowHovered, setIsRowHovered] = useState(false);
  const [isPrimaryCopied, setIsPrimaryCopied] = useState(false);
  const [isSecondaryHovered, setIsSecondaryHovered] = useState(false);

  const handlePrimaryCopy = useCallback(() => {
    navigator.clipboard.writeText(value)
      .then(() => {
        setIsPrimaryCopied(true);
        setTimeout(() => setIsPrimaryCopied(false), 2000);
      })
      .catch((error) => {
        console.error('Failed to copy enrichment value:', error);
      });
  }, [value]);

  const handlePrimaryKeyDown = useCallback((event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return;
    }
    event.preventDefault();
    handlePrimaryCopy();
  }, [handlePrimaryCopy]);

  const primaryIconClasses = cn(
    'h-3 w-3 shrink-0 transition-opacity text-default-font',
    {
      'opacity-0': !(isPrimaryCopied || (isRowHovered && !isSecondaryHovered)),
      'opacity-100': isPrimaryCopied || (isRowHovered && !isSecondaryHovered),
    }
  );

  const primaryIcon = isPrimaryCopied
    ? <Check className={primaryIconClasses} />
    : <Copy className={primaryIconClasses} />;

  return (
    <div
      className="flex cursor-pointer items-start gap-2 rounded-md bg-neutral-200 px-2.5 py-2"
      onMouseEnter={() => setIsRowHovered(true)}
      onMouseLeave={() => {
        setIsRowHovered(false);
        setIsSecondaryHovered(false);
      }}
      onClick={handlePrimaryCopy}
      onKeyDown={handlePrimaryKeyDown}
      title={`Click to copy: ${value}`}
      role="button"
      tabIndex={0}
    >
      <span className="mt-0.5 text-subtext-color">{icon}</span>
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-[11px] font-medium uppercase tracking-wide text-subtext-color">
          {label}
        </span>
        <div className="flex items-start gap-1">
          <span className="break-all text-body font-body text-default-font">{value}</span>
          {primaryIcon}
        </div>
        {secondary && (
          <CopyableInfoText
            value={secondary}
            tone="secondary"
            onHoverChange={setIsSecondaryHovered}
          />
        )}
      </div>
    </div>
  );
}

function CopyableInfoText({
  value,
  tone,
  onHoverChange,
}: {
  value: string;
  tone: 'primary' | 'secondary';
  onHoverChange?: (isHovered: boolean) => void;
}) {
  const [isHovered, setIsHovered] = useState(false);
  const [isCopied, setIsCopied] = useState(false);

  const handleMouseEnter = useCallback(() => {
    setIsHovered(true);
    onHoverChange?.(true);
  }, [onHoverChange]);

  const handleMouseLeave = useCallback(() => {
    setIsHovered(false);
    onHoverChange?.(false);
  }, [onHoverChange]);

  const handleCopyValue = useCallback((event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    navigator.clipboard.writeText(value)
      .then(() => {
        setIsCopied(true);
        setTimeout(() => setIsCopied(false), 2000);
      })
      .catch((error) => {
        console.error('Failed to copy enrichment value:', error);
      });
  }, [value]);

  const iconClasses = cn(
    'h-3 w-3 shrink-0 transition-opacity',
    tone === 'primary' ? 'text-default-font' : 'text-subtext-color',
    { 'opacity-0': !isHovered && !isCopied, 'opacity-100': isHovered || isCopied }
  );

  const textClasses = tone === 'primary'
    ? 'break-all text-body font-body text-default-font'
    : 'break-all text-caption font-caption text-subtext-color';

  const actionIcon = isCopied ? <Check className={iconClasses} /> : <Copy className={iconClasses} />;

  return (
    <button
      type="button"
      className="flex w-fit max-w-full items-start gap-1 rounded-sm text-left"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleCopyValue}
      title={`Click to copy: ${value}`}
    >
      <span className={textClasses}>{value}</span>
      {actionIcon}
    </button>
  );
}
