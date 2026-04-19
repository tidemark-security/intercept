/**
 * Icon Mapping Utility
 *
 * Maps string icon names from the database to React components.
 * This allows the backend to store icon identifiers as strings
 * while the frontend renders the actual Lucide React components.
 *
 * Uses lucide-react/dynamicIconImports to avoid bundling all ~1,500 icons.
 * Each icon is loaded on demand (~1-2 kB per icon).
 */

import React, { lazy, Suspense, memo } from 'react';
import dynamicIconImports from 'lucide-react/dynamicIconImports';
import { MSTeamsIcon, VirusTotalIcon } from '@/assets';

/**
 * Convert PascalCase icon name (as stored in DB) to kebab-case
 * (as used by lucide-react/dynamicIconImports).
 *
 * e.g. "AlertCircle" → "alert-circle", "WifiOff" → "wifi-off"
 */
function toKebabCase(name: string): string {
  return name
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/([A-Z])([A-Z][a-z])/g, '$1-$2')
    .toLowerCase();
}

type AnyComponent = React.ComponentType<any>;

// Cache for lazy components so we don't recreate them on every render
const componentCache = new Map<string, AnyComponent>();

function getLazyIcon(kebabName: string): AnyComponent | null {
  const cached = componentCache.get(kebabName);
  if (cached) return cached;

  const importFn = (dynamicIconImports as Record<string, () => Promise<{ default: AnyComponent }>>)[kebabName];
  if (!importFn) return null;

  const LazyIcon = lazy(importFn);
  componentCache.set(kebabName, LazyIcon);
  return LazyIcon;
}

/**
 * Small wrapper that renders a dynamically-imported Lucide icon.
 * Returns null (via Suspense fallback) while loading — icons are tiny
 * so the flash is imperceptible.
 */
const DynamicIcon = memo(function DynamicIcon({ name }: { name: string }) {
  const kebab = toKebabCase(name);
  const Icon = getLazyIcon(kebab);
  if (!Icon) return null;

  return (
    <Suspense fallback={null}>
      <Icon size="1em" />
    </Suspense>
  );
});

// Custom (non-Lucide) icons handled separately
const CUSTOM_ICONS: Record<string, React.ReactNode> = {
  MSTeamsIcon: <MSTeamsIcon />,
  VirusTotalIcon: <VirusTotalIcon />,
};

/**
 * Get a React icon element from a string name.
 *
 * @param iconName - PascalCase identifier for the icon (e.g. 'Mail', 'AlertCircle')
 * @returns React element or null if not found
 */
export function getIconComponent(iconName: string): React.ReactNode {
  if (iconName in CUSTOM_ICONS) return CUSTOM_ICONS[iconName];
  return <DynamicIcon name={iconName} />;
}

/**
 * Get all available icon names (PascalCase).
 *
 * Converts kebab-case keys from lucide-react back to PascalCase to match
 * the DB convention, plus custom icons.
 */
export function getAvailableIconNames(): string[] {
  const lucideNames = Object.keys(dynamicIconImports).map((kebab) =>
    kebab
      .split('-')
      .map((seg) => seg.charAt(0).toUpperCase() + seg.slice(1))
      .join('')
  );
  return [...lucideNames, ...Object.keys(CUSTOM_ICONS)];
}
