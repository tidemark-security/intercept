import { useQuery } from "@tanstack/react-query";
import { UserLinkTemplatesService } from "@/services/userLinkTemplatesService";
import type { ResolvedLinkTemplateRead } from "@/types/userLinkTemplates";
import type { GeneratedLink } from "@/utils/linkTemplates";
import { getIconComponent } from "@/utils/iconMapping";

export const userLinkTemplatePreferenceQueryKey = ["user-link-template-preferences"] as const;
export const resolvedLinkTemplateQueryKey = ["resolved-link-templates"] as const;

export function convertResolvedLinkTemplate(apiTemplate: ResolvedLinkTemplateRead): GeneratedLink {
  return {
    id: String(apiTemplate.id),
    name: apiTemplate.name,
    icon: getIconComponent(apiTemplate.icon_name),
    tooltip: apiTemplate.tooltip,
    url: apiTemplate.url,
  };
}

export function useUserLinkTemplatePreferences() {
  return useQuery({
    queryKey: userLinkTemplatePreferenceQueryKey,
    queryFn: () => UserLinkTemplatesService.listUserLinkTemplatePreferences(),
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });
}

export function useResolvedLinkTemplates(
  item: Record<string, unknown> | null | undefined,
  enabled: boolean = true,
) {
  const itemKey = item ? JSON.stringify(item) : "";

  return useQuery({
    queryKey: [...resolvedLinkTemplateQueryKey, itemKey],
    queryFn: async () => {
      const links = await UserLinkTemplatesService.resolveLinkTemplates({
        requestBody: { item: item || {} },
      });
      return links.map(convertResolvedLinkTemplate);
    },
    enabled: enabled && Boolean(item),
    staleTime: 60 * 1000,
    gcTime: 5 * 60 * 1000,
  });
}
