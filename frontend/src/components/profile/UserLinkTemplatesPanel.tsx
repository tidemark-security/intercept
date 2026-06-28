import type { ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LinkTemplateManager } from "@/components/link-templates";
import { resolvedLinkTemplateQueryKey } from "@/hooks/useUserLinkTemplates";
import { PersonalLinkTemplatesService } from "@/types/generated/services/PersonalLinkTemplatesService";
import type { PersonalLinkTemplateCreate, PersonalLinkTemplateUpdate } from "@/types/generated";
import type { PortableLinkTemplate } from "@/types/generated/models/PortableLinkTemplate";

const PERSONAL_LINK_TEMPLATE_QUERY_KEY = ["personal-link-templates"] as const;

export function UserLinkTemplatesPanel({
  showHeader = true,
  headerIcon,
  headerVariant = "default",
}: {
  showHeader?: boolean;
  headerIcon?: ReactNode;
  headerVariant?: "default" | "settings-card";
}) {
  const queryClient = useQueryClient();
  const { data: templates = [], isLoading } = useQuery({
    queryKey: PERSONAL_LINK_TEMPLATE_QUERY_KEY,
    queryFn: () =>
      PersonalLinkTemplatesService.getPersonalLinkTemplatesApiV1PersonalLinkTemplatesGet({
        enabledOnly: false,
      }),
    staleTime: 5 * 60 * 1000,
  });

  const invalidateTemplates = () => {
    queryClient.invalidateQueries({ queryKey: PERSONAL_LINK_TEMPLATE_QUERY_KEY });
    queryClient.invalidateQueries({ queryKey: resolvedLinkTemplateQueryKey });
  };

  return (
    <LinkTemplateManager
      title={showHeader ? "Personal Link Templates" : undefined}
      description={showHeader ? "Create private contextual action templates for your own workflow." : undefined}
      headerIcon={headerIcon}
      headerVariant={headerVariant}
      templates={templates}
      isLoading={isLoading}
      createLabel="Add Personal Template"
      emptyLabel="No personal link templates found."
      onCreate={(template: PortableLinkTemplate) =>
        PersonalLinkTemplatesService.createPersonalLinkTemplateApiV1PersonalLinkTemplatesPost({
          requestBody: template as PersonalLinkTemplateCreate,
        })
      }
      onUpdate={(templateId: number, template: Partial<PortableLinkTemplate>) =>
        PersonalLinkTemplatesService.updatePersonalLinkTemplateApiV1PersonalLinkTemplatesTemplateIdPatch({
          templateId,
          requestBody: template as PersonalLinkTemplateUpdate,
        })
      }
      onDelete={(templateId: number) =>
        PersonalLinkTemplatesService.deletePersonalLinkTemplateApiV1PersonalLinkTemplatesTemplateIdDelete({
          templateId,
        })
      }
      onImport={(payload: unknown) =>
        PersonalLinkTemplatesService.importPersonalLinkTemplatesApiV1PersonalLinkTemplatesImportPost({
          requestBody: payload,
        })
      }
      onExport={(templateIds: number[]) =>
        PersonalLinkTemplatesService.exportPersonalLinkTemplatesApiV1PersonalLinkTemplatesExportPost({
          requestBody: { template_ids: templateIds },
        })
      }
      onChanged={invalidateTemplates}
    />
  );
}
