/**
 * LinkButton Component
 * 
 * A button that opens a link in a new tab with configurable icon and tooltip.
 * Built on top of IconButton for consistent styling.
 */

import React from 'react';
import { IconButton } from '@/components/buttons/IconButton';
import { Tooltip } from '@/components/overlays/Tooltip';

export interface LinkButtonProps {
  /** URL to open */
  href: string;
  
  /** Icon to display */
  icon: React.ReactNode;
  
  /** Tooltip text */
  tooltip?: string;
  
  /** Button variant (default: 'neutral-tertiary') */
  variant?: 'neutral-tertiary' | 'brand-tertiary' | 'destructive-tertiary';
  
  /** Button size (default: 'small') */
  size?: 'small' | 'medium' | 'large';
  
  /** Optional className for additional styling */
  className?: string;
  
  /** Click handler (called before opening link) */
  onClick?: (e: React.MouseEvent) => void;
}

/**
 * LinkButton component
 * 
 * Renders an IconButton that opens a URL in a new tab when clicked.
 * Prevents event propagation to avoid triggering parent click handlers.
 * 
 * @example
 * ```tsx
 * <LinkButton
 *   href="mailto:user@example.com"
 *   icon={<FeatherMail />}
 *   tooltip="Email user@example.com"
 * />
 * ```
 */
export function LinkButton({
  href,
  icon,
  tooltip,
  variant = 'neutral-tertiary',
  size = 'small',
  className,
  onClick,
}: LinkButtonProps) {
  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent parent click handlers
    
    // Call custom onClick if provided
    if (onClick) {
      onClick(e);
    }
    
    // Open link in new tab
    window.open(href, '_blank', 'noopener,noreferrer');
  };

  const button = (
    <IconButton
      icon={icon}
      variant={variant}
      size={size}
      onClick={handleClick}
      className={className}
      aria-label={tooltip}
    />
  );

  // If no tooltip, just return the button
  if (!tooltip) {
    return button;
  }

  // Wrap with Radix tooltip
  return (
    <Tooltip.Provider>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          {button}
        </Tooltip.Trigger>
        <Tooltip.Content
          side="bottom"
          align="center"
          sideOffset={8}
        >
          {tooltip}
        </Tooltip.Content>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}
