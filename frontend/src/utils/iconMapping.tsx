/**
 * Icon Mapping Utility
 *
 * Maps string icon names from the database to React components.
 * This allows the backend to store icon identifiers as strings
 * while the frontend renders the actual Lucide React components.
 *
 * Uses a small custom icon registry for provider-specific icons, then
 * lucide-react/dynamicIconImports to avoid bundling all ~1,500 lucide icons.
 * Each lucide icon is loaded on demand (~1-2 kB per icon).
 */

import React, { lazy, Suspense, memo } from 'react';
import dynamicIconImports from 'lucide-react/dynamicIconImports';
import { BoxSelect } from 'lucide-react';
import { MSTeamsIcon, VirusTotalIcon } from '@/assets';

export const FALLBACK_LINK_TEMPLATE_ICON = 'BoxSelect';

const CUSTOM_LINK_TEMPLATE_ICONS = {
  MSTeamsIcon,
  VirusTotalIcon,
} satisfies Record<string, React.ComponentType<React.HTMLAttributes<HTMLElement>>>;

type CustomLinkTemplateIconName = keyof typeof CUSTOM_LINK_TEMPLATE_ICONS;

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

function hasLucideIcon(name: string): boolean {
  return toKebabCase(name) in dynamicIconImports;
}

function hasCustomIcon(name: string): name is CustomLinkTemplateIconName {
  return name in CUSTOM_LINK_TEMPLATE_ICONS;
}

export function normalizeLinkTemplateIconName(iconName: string | null | undefined): string {
  return iconName && (hasCustomIcon(iconName) || hasLucideIcon(iconName))
    ? iconName
    : FALLBACK_LINK_TEMPLATE_ICON;
}

/**
 * Small wrapper that renders a dynamically-imported Lucide icon.
 * Returns null (via Suspense fallback) while loading — icons are tiny
 * so the flash is imperceptible.
 */
const DynamicIcon = memo(function DynamicIcon({ name }: { name: string }) {
  if (hasCustomIcon(name)) {
    const CustomIcon = CUSTOM_LINK_TEMPLATE_ICONS[name];
    return <CustomIcon />;
  }

  const kebab = toKebabCase(name);
  const Icon = getLazyIcon(kebab);
  if (!Icon) return <BoxSelect size="1em" />;

  return (
    <Suspense fallback={null}>
      <Icon size="1em" />
    </Suspense>
  );
});

/**
 * Get a React icon element from a string name.
 *
 * @param iconName - PascalCase identifier for the icon (e.g. 'Mail', 'AlertCircle')
 * @returns React element. Unknown names fall back to BoxSelect.
 */
export function getIconComponent(iconName: string): React.ReactNode {
  return <DynamicIcon name={normalizeLinkTemplateIconName(iconName)} />;
}

/**
 * Get all available icon names (PascalCase).
 *
 * Converts kebab-case keys from lucide-react back to PascalCase to match
 * the DB convention, plus custom icons.
 */
export function getAvailableIconNames(): string[] {
  const lucideNames = Object.keys(dynamicIconImports)
    .map((kebab) =>
      kebab
        .split('-')
        .map((seg) => seg.charAt(0).toUpperCase() + seg.slice(1))
        .join('')
    )
    .sort((a, b) => a.localeCompare(b));
  const customNames = Object.keys(CUSTOM_LINK_TEMPLATE_ICONS);
  const searchableNames = Array.from(
    new Set([...customNames, ...lucideNames].filter((name) => name !== FALLBACK_LINK_TEMPLATE_ICON)),
  ).sort((a, b) => a.localeCompare(b));

  return [
    FALLBACK_LINK_TEMPLATE_ICON,
    ...searchableNames,
  ];
}
