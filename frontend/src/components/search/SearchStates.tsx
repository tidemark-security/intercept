import React from 'react';
import { Search, X } from 'lucide-react';
import { Button } from '@/components/buttons/Button';
import { IconWithBackground } from '@/components/misc/IconWithBackground';

type SearchStateVariant = 'modal' | 'page';

interface SearchPromptProps {
  variant?: SearchStateVariant;
}

interface NoResultsProps {
  query: string;
  variant?: SearchStateVariant;
}

interface SearchErrorProps {
  error: Error | null;
  onRetry: () => void;
  variant?: SearchStateVariant;
}

export function SearchPrompt({ variant = 'modal' }: SearchPromptProps) {
  if (variant === 'page') {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center w-full">
        <IconWithBackground variant="neutral" size="large" icon={<Search />} />
        <p className="pt-5 text-lg font-medium text-default-font">Search alerts, cases, and tasks</p>
        <p className="text-sm text-subtext-color mt-2 max-w-md">
          Type at least 2 characters to search, or use * to run filter-only search. Results include title, description, and timeline content.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-8 text-center w-full">
      <p className="text-sm font-medium text-default-font">No search specified</p>
      <p className="text-xs text-subtext-color mt-1">
        Type at least 2 characters to search, or use * for filter-only search.
      </p>
    </div>
  );
}

export function NoResults({ query, variant = 'modal' }: NoResultsProps) {
  if (variant === 'page') {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center w-full">
        <div className="h-12 w-12 rounded-full bg-neutral-100 flex items-center justify-center mb-4">
          <Search className="h-6 w-6 text-subtext-color" />
        </div>
        <p className="text-lg font-medium text-default-font">No results found</p>
        <p className="text-sm text-subtext-color mt-2 max-w-md">
          No matches for "{query}". Try different keywords or adjust your filters.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-8 text-center w-full">
      <p className="text-sm font-medium text-default-font">No results found</p>
      <p className="text-xs text-subtext-color mt-1">
        No matches for "{query}". Try different keywords.
      </p>
    </div>
  );
}

export function SearchError({ error, onRetry, variant = 'modal' }: SearchErrorProps) {
  const isPage = variant === 'page';

  return (
    <div className={isPage ? 'flex flex-col items-center justify-center py-16 text-center px-4' : 'flex flex-col items-center justify-center py-8 text-center px-4'}>
      <div className={isPage ? 'h-12 w-12 rounded-full bg-error-100 flex items-center justify-center mb-4' : 'h-8 w-8 rounded-full bg-error-100 flex items-center justify-center mb-2'}>
        <X className={isPage ? 'h-6 w-6 text-error-600' : 'h-4 w-4 text-error-600'} />
      </div>
      <p className={isPage ? 'text-lg font-medium text-default-font' : 'text-sm font-medium text-default-font'}>Search failed</p>
      <p className={isPage ? 'text-sm text-subtext-color mt-2 max-w-md' : 'text-xs text-subtext-color mt-1 max-w-xs'}>
        {error?.message || 'Unable to perform search. Please try again.'}
      </p>
      <Button onClick={onRetry} variant="brand-secondary" size="small" className={isPage ? 'mt-4' : 'mt-3'}>
        Try again
      </Button>
    </div>
  );
}
