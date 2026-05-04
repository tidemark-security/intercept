import React from 'react';

import { Tag } from '@/components/data-display/Tag';
import { cn } from '@/utils/cn';

interface TimelineDescriptionBlockProps {
  children: React.ReactNode;
  actionButtons?: React.ReactNode;
  tags?: string[] | null;
  tagContent?: React.ReactNode;
  className?: string;
  variant?: 'timeline' | 'metadata';
}

export function TimelineDescriptionBlock({
  children,
  actionButtons,
  tags,
  tagContent,
  className,
  variant = 'timeline',
}: TimelineDescriptionBlockProps) {
  const descriptionContent = React.Children.toArray(children);
  const hasDescriptionContent = descriptionContent.length > 0;
  const visibleTags = React.useMemo(
    () => (tags || []).map(tag => tag.trim()).filter(Boolean),
    [tags],
  );
  const hasTags = visibleTags.length > 0;
  const renderedTagContent = tagContent || (hasTags ? visibleTags.map((tag, index) => (
    <Tag key={`${tag}-${index}`} tagText={tag} showDelete={false} p="0" />
  )) : null);
  const hasTagContent = !!renderedTagContent;

  return (
    <div
      className={cn(
        'border-t border-solid border-neutral-border bg-neutral-500/5 py-3',
        variant === 'timeline'
          ? '-mx-4 -mb-3 w-[calc(100%+2rem)] px-4'
          : '-mx-6 -mb-6 w-[calc(100%+3rem)] px-6 border-x border-x-default-background mobile:-mx-4 mobile:-mb-4 mobile:w-[calc(100%+2rem)] mobile:px-4',
        className,
      )}
    >
      <div className="flex w-full flex-col gap-3">
        {hasDescriptionContent ? (
          <div className="w-full text-body font-body text-default-font">
            {descriptionContent}
          </div>
        ) : null}
        {hasTagContent ? (
          <div
            className="flex w-full flex-wrap items-center gap-1.5"
            aria-label="Tags"
          >
            {renderedTagContent}
          </div>
        ) : null}
        {actionButtons ? (
          <div
            className={cn(
              'flex w-full flex-col items-start',
              (hasDescriptionContent || hasTagContent) && 'border-t border-solid border-neutral-border pt-3',
            )}
          >
            {actionButtons}
          </div>
        ) : null}
      </div>
    </div>
  );
}