import React from 'react';

import { cn } from '@/utils/cn';

interface TimelineDescriptionBlockProps {
  children: React.ReactNode;
  actionButtons?: React.ReactNode;
  className?: string;
}

export function TimelineDescriptionBlock({
  children,
  actionButtons,
  className,
}: TimelineDescriptionBlockProps) {
  const hasDescriptionContent = React.Children.toArray(children).length > 0;

  return (
    <div
      className={cn(
        '-mx-4 -mb-3 w-[calc(100%+2rem)] border-t border-solid border-neutral-border bg-neutral-500/10 px-4 py-3',
        className,
      )}
    >
      <div className="flex w-full flex-col gap-3">
        {children}
        {actionButtons ? (
          <div
            className={cn(
              'flex w-full flex-col items-start',
              hasDescriptionContent && 'border-t border-solid border-neutral-border pt-3',
            )}
          >
            {actionButtons}
          </div>
        ) : null}
      </div>
    </div>
  );
}