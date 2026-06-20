import React from 'react';
import { X } from 'lucide-react';
import { cn } from '@/utils/cn';

export function getTagSearchHref(tag: string): string {
  const params = new URLSearchParams();
  params.append('tag', tag);
  return `/search?${params.toString()}`;
}

interface ConditionalDeleteButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  mode?: 'default' | 'light' | 'dark';
}

const ConditionalDeleteButton = React.forwardRef<HTMLButtonElement, ConditionalDeleteButtonProps>(
  function ConditionalDeleteButton({ mode = 'default', className, onClick, ...otherProps }, ref) {
    return (
      <button
        type="button"
        className={cn(
          'group/5b6b02a2 flex cursor-pointer items-center gap-2 hover:bg-[#ffffff33]',
          { 'hover:bg-[#00000033]': mode === 'dark' },
          className,
        )}
        ref={ref}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          onClick?.(event);
        }}
        {...otherProps}
      >
        <X className={cn('text-body font-body text-white', { 'text-black': mode === 'dark' })} />
      </button>
    );
  },
);

export interface TagProps extends React.HTMLAttributes<HTMLSpanElement> {
  tagText?: React.ReactNode;
  showDelete?: boolean;
  p?: 'default' | '0' | '1' | '2' | '3' | '4' | '5';
  onDelete?: () => void;
  searchHref?: string;
  searchable?: boolean;
}

const TagRoot = React.forwardRef<HTMLSpanElement, TagProps>(function TagRoot(
  {
    tagText,
    showDelete = false,
    p = 'default',
    className,
    onClick,
    onAuxClick,
    onDelete,
    searchHref,
    searchable = true,
    ...otherProps
  },
  ref,
) {
  const tagSearchHref =
    searchable && typeof tagText === 'string' && tagText.trim()
      ? searchHref ?? getTagSearchHref(tagText.trim())
      : undefined;
  const textClassName = cn(
    'line-clamp-1 flex h-full grow shrink-0 basis-0 items-center justify-center overflow-hidden text-ellipsis text-center text-caption font-caption',
    {
      'cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-primary': Boolean(tagSearchHref),
      'text-[#0A0A0A]': p === '5',
      'text-[#0A0F0D]': p === '4',
      'text-black': p === 'default' || p === '3' || p === '2',
      'text-white': p === '1' || p === '0',
    },
  );

  return (
    <span
      className={cn(
        'group/02c10a66 flex h-6 items-center justify-center gap-1 border bevel-br-md border-solid border-neutral-border bg-brand-100 px-2',
        'hover:border-brand-primary',
        {
          'bg-p5': p === '5',
          'bg-p4': p === '4',
          'bg-p3': p === '3',
          'bg-p2': p === '2',
          'bg-p1': p === '1',
          'bg-p0': p === '0',
        },
        className,
      )}
      ref={ref}
      onClick={(event) => {
        event.stopPropagation();
        onClick?.(event);
      }}
      onAuxClick={(event) => {
        event.stopPropagation();
        onAuxClick?.(event);
      }}
      {...otherProps}
    >
      {tagText && tagSearchHref ? (
        <a
          className={textClassName}
          href={tagSearchHref}
          onClick={(event) => {
            event.stopPropagation();
          }}
          onAuxClick={(event) => {
            event.stopPropagation();
          }}
        >
          {tagText}
        </a>
      ) : tagText ? (
        <span className={textClassName}>{tagText}</span>
      ) : null}
      <span className={cn('hidden h-4 w-4 flex-none items-center justify-center gap-1', { flex: showDelete })}>
        <ConditionalDeleteButton
          aria-label={typeof tagText === 'string' ? `Remove ${tagText}` : 'Remove tag'}
          className={cn('hidden', { flex: showDelete })}
          mode={p === '5' || p === '4' || p === '3' || p === '2' ? 'dark' : 'light'}
          onClick={onDelete}
        />
      </span>
    </span>
  );
});

export const Tag = Object.assign(TagRoot, {
  ConditionalDeleteButton,
});
