import { useId, type ReactNode } from 'react';

import { Button } from '@/components/buttons/Button';
import { useTheme } from '@/contexts/ThemeContext';
import { cn } from '@/utils/cn';
import { IconWrapper } from '@/utils/IconWrapper';

interface TriageStatusCardProps {
  title: string;
  description: string;
  icon: ReactNode;
  appearance?: 'available' | 'failed' | 'processing';
  action?: { label: string; onClick: () => void; busy?: boolean; icon?: ReactNode };
}

export function TriageStatusCard({ title, description, icon, appearance = 'available', action }: TriageStatusCardProps) {
  const titleId = useId();
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';
  const appearanceClasses = {
    available: {
      surface: 'border-dashed border-neutral-border bg-neutral-50',
      title: 'text-default-font',
      description: 'text-subtext-color',
    },
    failed: {
      surface: 'border-solid border-error-200 bg-error-50',
      title: 'text-error-700',
      description: 'text-error-700',
    },
    processing: {
      surface: isDarkTheme ? 'border-solid border-brand-primary bg-brand-900' : 'border-solid border-brand-800 bg-brand-primary',
      title: isDarkTheme ? 'text-brand-primary' : 'text-brand-1000',
      description: isDarkTheme ? 'text-brand-primary' : 'text-brand-1000',
    },
  }[appearance];

  return (
    <section
      aria-labelledby={titleId}
      className={cn(
        'flex w-full min-w-0 flex-wrap items-center gap-x-4 gap-y-2 rounded-md border px-3 py-2',
        appearanceClasses.surface,
      )}
    >
      <div className={cn('flex min-w-0 flex-col gap-0.5', action ? 'flex-[1_1_16rem]' : 'flex-1')}>
        <div className={cn(
          'flex min-w-0 items-center gap-2',
          appearanceClasses.title,
        )}>
          <IconWrapper className="flex-none text-heading-3" aria-hidden="true">{icon}</IconWrapper>
          <h2 id={titleId} className="text-heading-3 font-heading-3">{title}</h2>
        </div>
        <p className={cn(
          'whitespace-pre-line text-caption font-caption [overflow-wrap:anywhere]',
          appearanceClasses.description,
        )}>
          {description}
        </p>
      </div>
      {action && (
        <Button
          size="medium"
          variant={appearance === 'failed' ? 'neutral-secondary' : 'brand-primary'}
          className="ml-auto flex-none"
          onClick={action.onClick}
          aria-label={action.label}
          aria-busy={action.busy}
          disabled={action.busy}
          loading={action.busy}
          icon={action.icon}
        >
          {action.label}
        </Button>
      )}
    </section>
  );
}
