import { createTailwindMerge, getDefaultConfig } from "tailwind-merge";

/**
 * Font mixins that need special conflict handling.
 * These custom utility classes should conflict with each other and with
 * standard Tailwind font-size, leading, and font-weight classes.
 */
const fontMixins = [
  // old font mixins
  "text-label",
  "text-label-bold",
  "text-body",
  "text-body-bold",
  "text-subheader",
  "text-section-header",
  "text-header",
  "text-monospace-body",

  // new font mixins
  "text-caption",
  "text-caption-bold",
  "text-heading-3",
  "text-heading-2",
  "text-heading-1",
];

/**
 * Custom tailwind-merge instance configured to handle font mixins.
 * This ensures font mixins properly conflict with each other and with
 * standard Tailwind typography classes.
 */
const customTwMerge = createTailwindMerge(() => {
  const defaultConfig = getDefaultConfig();

  return {
    ...defaultConfig,
    classGroups: {
      ...defaultConfig.classGroups,
      "font-mixins": fontMixins,
    },
    conflictingClassGroups: {
      ...defaultConfig.conflictingClassGroups,
      // font mixins conflict with standard typography classes
      "font-mixins": ["font-size", "leading", "font-weight"],
      "font-size": ["font-mixins"],
      leading: ["font-mixins"],
      "font-weight": ["font-mixins"],
    },
  };
});

/**
 * Utility for combining CSS classes with conditional support
 * 
  * Supports strings, booleans, undefined, null, and conditional object syntax
 * 
 * Uses tailwind-merge to intelligently resolve conflicting Tailwind classes
 * (e.g., "hidden flex" will correctly resolve to "flex" instead of being unpredictable)
 * 
 * Also handles font mixins (text-body, text-caption, etc.)
 * so they properly conflict with each other and with standard Tailwind typography.
 * 
 * @example
 * cn("base-class", { "active": isActive, "disabled": isDisabled }, optionalClass)
 * cn("hidden", { "flex": isVisible }) // Returns "flex" when isVisible is true
 * cn("text-body", "text-caption") // Returns "text-caption" (last wins)
 */
export function cn(
  ...classes: (string | boolean | undefined | null | Record<string, boolean>)[]
): string {
  const result = classes
    .flatMap((c) => {
      if (!c) return [];
      if (typeof c === "string") return c;
      if (typeof c === "object") {
        return Object.entries(c)
          .filter(([, v]) => v)
          .map(([k]) => k);
      }
      return [];
    })
    .join(" ");
  
  // Use custom tailwind-merge to resolve conflicting classes
  return customTwMerge(result);
}
