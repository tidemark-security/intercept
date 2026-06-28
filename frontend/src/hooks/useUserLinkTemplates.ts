import { useQuery } from "@tanstack/react-query";
import { LinkTemplatesService } from "@/types/generated/services/LinkTemplatesService";
import type { LinkTemplateResolveRequest } from "@/types/generated/models/LinkTemplateResolveRequest";
import type { ResolvedLinkTemplateRead } from "@/types/generated/models/ResolvedLinkTemplateRead";
import type { GeneratedLink } from "@/utils/linkTemplates";
import { getIconComponent } from "@/utils/iconMapping";

export const resolvedLinkTemplateQueryKey = ["resolved-link-templates"] as const;

export function convertResolvedLinkTemplate(apiTemplate: ResolvedLinkTemplateRead): GeneratedLink {
  return {
    id: `${apiTemplate.visibility}:${apiTemplate.id}`,
    name: apiTemplate.name,
    icon: getIconComponent(apiTemplate.icon_name),
    tooltip: apiTemplate.tooltip,
    url: apiTemplate.url,
  };
}

export type ResolvedLinkTemplateOptions = Pick<LinkTemplateResolveRequest, "surface" | "entity_type">;

function buildResolveRequest(
  item: Record<string, unknown> | null | undefined,
  options: ResolvedLinkTemplateOptions,
): LinkTemplateResolveRequest {
  return {
    surface: options.surface ?? "timeline_item",
    entity_type: options.entity_type ?? null,
    item: item || {},
  };
}

export function useResolvedLinkTemplates(
  item: Record<string, unknown> | null | undefined,
  enabled: boolean = true,
  options: ResolvedLinkTemplateOptions = {},
) {
  const itemKey = item ? JSON.stringify(item) : "";
  const surface = options.surface ?? "timeline_item";
  const entityType = options.entity_type ?? null;

  return useQuery({
    queryKey: [...resolvedLinkTemplateQueryKey, surface, entityType, itemKey],
    queryFn: async () => {
      const links = await LinkTemplatesService.resolveLinkTemplatesApiV1LinkTemplatesResolvePost({
        requestBody: buildResolveRequest(item, { surface, entity_type: entityType }),
      });
      return links.map(convertResolvedLinkTemplate);
    },
    enabled: enabled && Boolean(item),
    staleTime: 60 * 1000,
    gcTime: 5 * 60 * 1000,
  });
}
