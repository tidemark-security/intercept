import React from 'react';

import { formatRelativeTime } from '@/utils/dateFormatters';

interface RelativeTimeProps {
  value: string | Date | null | undefined;
  className?: string;
}

export function RelativeTime({ value, className }: RelativeTimeProps) {
  const relativeTime = formatRelativeTime(value);

  if (!relativeTime) {
    return null;
  }

  return <span className={className}>{relativeTime}</span>;
}

export default RelativeTime;
