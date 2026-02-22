/**
 * Link Template System
 * 
 * Provides a configuration-driven approach for generating contextual links
 * from timeline items. Link templates are loaded from the API and support
 * template interpolation for dynamic URLs, tooltips, and custom icons.
 * 
 * Example use cases:
 * - Click-to-call (tel: links)
 * - Click-to-chat (MS Teams, Slack deep links)
 * - Click-to-email (mailto: links)
 * - CMDB/ticketing system lookups
 * - External investigation tools
 */

import React from 'react';

/**
 * Link template configuration
 * 
 * Defines how to generate a link from timeline item data
 */
export interface LinkTemplate {
  /** Unique identifier for this template */
  id: string;
  
  /** Icon component to display in the button */
  icon: React.ReactNode;
  
  /** Tooltip text (supports {{variable}} interpolation) */
  tooltip: string;
  
  /** URL template (supports {{variable}} interpolation) */
  urlTemplate: string;
  
  /** Field names that this template applies to (for automatic detection) */
  fieldNames?: string[];
  
  /** Optional: field/value pairs that must match for this template to apply */
  conditions?: Record<string, any>;
  
  /** Optional: custom className for styling */
  className?: string;
}

/**
 * Interpolate template string with item data
 * 
 * Replaces {{fieldName}} with values from the item object.
 * Supports nested fields using dot notation: {{user.email}}
 * 
 * @param template - Template string with {{variable}} placeholders
 * @param item - Data object containing values
 * @returns Interpolated string
 * 
 * @example
 * ```ts
 * interpolateTemplate('Hello {{name}}', { name: 'Alice' })
 * // Returns: 'Hello Alice'
 * 
 * interpolateTemplate('{{user.email}}', { user: { email: 'alice@example.com' } })
 * // Returns: 'alice@example.com'
 * ```
 */
export function interpolateTemplate(template: string, item: any): string {
  return template.replace(/\{\{([^}]+)\}\}/g, (match, fieldPath) => {
    const trimmedPath = fieldPath.trim();
    
    // Support nested field access with dot notation
    const value = trimmedPath.split('.').reduce((obj: any, key: string) => {
      return obj?.[key];
    }, item);
    
    // Return the value if found, otherwise keep the placeholder
    return value !== undefined && value !== null ? String(value) : match;
  });
}

/**
 * URL encode a value for safe inclusion in URLs
 * 
 * @param value - Value to encode
 * @returns URL-encoded string
 */
export function urlEncode(value: string): string {
  return encodeURIComponent(value);
}

/**
 * Interpolate template and URL-encode the result
 * 
 * @param template - Template string
 * @param item - Data object
 * @returns URL-encoded interpolated string
 * 
 * Note: If the interpolated value is already a complete URL (starts with http://, https://, 
 * mailto:, tel:, etc.), it will NOT be encoded to preserve the URL structure.
 */
export function interpolateUrl(template: string, item: any): string {
  // If the template is just a single placeholder for a URL field, return the raw value
  // This handles cases like url_template: "{{url}}" where the value is already a complete URL
  const singlePlaceholderMatch = template.match(/^\{\{([^}]+)\}\}$/);
  if (singlePlaceholderMatch) {
    const fieldPath = singlePlaceholderMatch[1].trim();
    const value = fieldPath.split('.').reduce((obj: any, key: string) => {
      return obj?.[key];
    }, item);
    
    if (value !== undefined && value !== null) {
      const strValue = String(value);
      // If the value is already a URL, return it as-is
      if (/^(https?:|mailto:|tel:|slack:|msteams:)/i.test(strValue)) {
        return strValue;
      }
    }
  }
  
  // Encode each interpolated value
  // We need to re-parse to encode only the variable parts
  return template.replace(/\{\{([^}]+)\}\}/g, (match, fieldPath) => {
    const trimmedPath = fieldPath.trim();
    const value = trimmedPath.split('.').reduce((obj: any, key: string) => {
      return obj?.[key];
    }, item);
    
    return value !== undefined && value !== null ? urlEncode(String(value)) : match;
  });
}

/**
 * Check if a link template should be displayed for an item
 * 
 * @param template - Link template configuration
 * @param item - Timeline item data
 * @returns True if the link should be shown
 */
export function shouldShowLink(template: LinkTemplate, item: any): boolean {
  // Check conditions (field/value matches)
  if (template.conditions) {
    for (const [field, expectedValue] of Object.entries(template.conditions)) {
      if (item[field] !== expectedValue) {
        return false;
      }
    }
  }
  
  return true;
}

/**
 * Generate a complete link configuration from a template and item
 * 
 * @param template - Link template configuration
 * @param item - Timeline item data
 * @returns Object with interpolated URL and tooltip, or null if shouldn't show
 */
export function generateLink(
  template: LinkTemplate,
  item: any
): { url: string; tooltip: string; icon: React.ReactNode; id: string; className?: string } | null {
  if (!shouldShowLink(template, item)) {
    return null;
  }

  return {
    id: template.id,
    url: interpolateUrl(template.urlTemplate, item),
    tooltip: interpolateTemplate(template.tooltip, item),
    icon: template.icon,
    className: template.className,
  };
}

/**
 * Generate multiple links from an array of templates
 * 
 * @param templates - Array of link template configurations
 * @param item - Timeline item data
 * @returns Array of generated link configurations
 */
export function generateLinks(
  templates: LinkTemplate[],
  item: any
): Array<{ url: string; tooltip: string; icon: React.ReactNode; id: string; className?: string }> {
  return templates
    .map(template => generateLink(template, item))
    .filter((link): link is NonNullable<typeof link> => link !== null);
}

/**
 * Automatically detect which link templates apply to an item based on its fields
 * 
 * @param templates - Array of available link templates (from API)
 * @param item - Timeline item data
 * @returns Array of applicable link templates
 */
export function detectLinkTemplates(templates: LinkTemplate[], item: any): LinkTemplate[] {
  if (!item || !templates) return [];
  
  const itemFields = Object.keys(item);
  const applicableTemplates: LinkTemplate[] = [];
  
  for (const template of templates) {
    if (!template.fieldNames || template.fieldNames.length === 0) continue;
    
    // Check if any of the template's field names exist in the item
    const hasMatchingField = template.fieldNames.some((fieldName: string) => 
      itemFields.includes(fieldName) && item[fieldName] != null
    );
    
    if (hasMatchingField) {
      applicableTemplates.push(template);
    }
  }
  
  return applicableTemplates;
}

/**
 * Automatically generate links based on item fields
 * 
 * @param templates - Array of available link templates (from API)
 * @param item - Timeline item data
 * @returns Array of generated link configurations
 */
export function generateAutoLinks(
  templates: LinkTemplate[],
  item: any
): Array<{ url: string; tooltip: string; icon: React.ReactNode; id: string; className?: string }> {
  const applicableTemplates = detectLinkTemplates(templates, item);
  return generateLinks(applicableTemplates, item);
}
