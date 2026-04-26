import React, { lazy, Suspense } from 'react';

const LazyEditor = lazy(() =>
  import('@tidemark-security/ux').then(m => ({ default: m.MarkdownInput }))
);

/**
 * Lazy wrapper around the heavy MDX editor.
 * The actual editor chunk is loaded on demand when a form mounts this component.
 */
export const MarkdownInput = React.forwardRef<
  HTMLDivElement,
  Omit<React.HTMLAttributes<HTMLDivElement>, 'onChange'> & {
    variant?: "default" | "compact";
    className?: string;
    value?: string;
    onChange?: (value?: string) => void;
    autoFocus?: boolean;
  }
>(function MarkdownInput(props, ref) {
  return (
    <Suspense fallback={<div className="w-full min-h-[120px]" />}>
      <LazyEditor {...props} ref={ref} />
    </Suspense>
  );
});
