import React from 'react';

/** Link data resolved by the backend from public and personal link templates. */
export interface GeneratedLink {
  url: string;
  tooltip: string;
  icon: React.ReactNode;
  id: string;
  name?: string;
  className?: string;
}
