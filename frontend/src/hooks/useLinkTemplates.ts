/**
 * Link Templates Hook
 * 
 * Provides React hooks for fetching and managing link templates from the API.
 * Uses TanStack Query for caching and state management.
 */

import { useQuery } from '@tanstack/react-query';
import { LinkTemplatesService } from '@/types/generated/services/LinkTemplatesService';
import type { LinkTemplateRead } from '@/types/generated/models/LinkTemplateRead';
import type { LinkTemplate } from '@/utils/linkTemplates';
import { getIconComponent } from '@/utils/iconMapping';

/**
 * Convert API LinkTemplateRead to frontend LinkTemplate format
 * 
 * @param apiTemplate - Template from API
 * @returns Frontend LinkTemplate with React icon component
 */
export function convertApiTemplate(apiTemplate: LinkTemplateRead): LinkTemplate {
  return {
    id: apiTemplate.template_id,
    icon: getIconComponent(apiTemplate.icon_name),
    tooltip: apiTemplate.tooltip_template,
    urlTemplate: apiTemplate.url_template,
    fieldNames: apiTemplate.field_names || undefined,
    conditions: apiTemplate.conditions || undefined,
  };
}

/**
 * Fetch link templates from the API
 * 
 * @param enabledOnly - If true, only fetch enabled templates (default: true)
 * @returns TanStack Query result with link templates
 */
export function useLinkTemplates(enabledOnly: boolean = true) {
  return useQuery({
    queryKey: ['link-templates', enabledOnly],
    queryFn: async () => {
      const apiTemplates = await LinkTemplatesService.getLinkTemplatesApiV1LinkTemplatesGet({
        enabledOnly,
      });
      return apiTemplates.map(convertApiTemplate);
    },
    staleTime: 5 * 60 * 1000, // 5 minutes - templates don't change often
    gcTime: 10 * 60 * 1000, // 10 minutes (formerly cacheTime)
  });
}

/**
 * Get a specific link template by ID
 * 
 * @param templateId - Database ID of the template
 * @returns TanStack Query result with single link template
 */
export function useLinkTemplate(templateId: number) {
  return useQuery({
    queryKey: ['link-template', templateId],
    queryFn: async () => {
      const apiTemplate = await LinkTemplatesService.getLinkTemplateApiV1LinkTemplatesTemplateIdGet({
        templateId,
      });
      return convertApiTemplate(apiTemplate);
    },
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });
}
