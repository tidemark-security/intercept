import { AlertCircle } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";
import { AdminPageLayout } from "@/components/layout/AdminPageLayout";
import { LinkTemplateManager } from "@/components/link-templates";
import { useSession } from "@/contexts/sessionContext";
import { LinkTemplatesService } from "@/types/generated/services/LinkTemplatesService";
import type { LinkTemplateCreate, LinkTemplateUpdate } from "@/types/generated";
import type { PortableLinkTemplate } from "@/types/generated/models/PortableLinkTemplate";

const PUBLIC_LINK_TEMPLATE_QUERY_KEY = ["admin-link-templates"] as const;

function AdminLinkTemplates() {
  const { user: currentUser } = useSession();
  const queryClient = useQueryClient();
  const isAdmin = currentUser?.role === "ADMIN";

  const { data: templates = [], isLoading } = useQuery({
    queryKey: PUBLIC_LINK_TEMPLATE_QUERY_KEY,
    queryFn: () =>
      LinkTemplatesService.getLinkTemplatesApiV1LinkTemplatesGet({
        enabledOnly: false,
      }),
    enabled: isAdmin,
  });

  const invalidateTemplates = () => {
    queryClient.invalidateQueries({ queryKey: PUBLIC_LINK_TEMPLATE_QUERY_KEY });
    queryClient.invalidateQueries({ queryKey: ["resolved-link-templates"] });
  };

  if (!isAdmin) {
    return (
      <DefaultPageLayout>
        <div className="mx-auto flex h-full w-full max-w-[1536px] flex-col items-center justify-center gap-4 bg-default-background px-6 mobile:px-4">
          <AlertCircle className="text-[48px] text-error text-error-500" />
          <span className="text-heading-2 font-heading-2 text-default-font">Access Denied</span>
          <span className="text-body font-body text-subtext-color">
            Admin privileges required to manage link templates
          </span>
        </div>
      </DefaultPageLayout>
    );
  }

  return (
    <AdminPageLayout
      title="Link Templates"
      subtitle="Manage public contextual action templates"
    >
      <LinkTemplateManager
        description="Public templates are available to every analyst when their scope and conditions match."
        templates={templates}
        isLoading={isLoading}
        createLabel="Add Public Template"
        emptyLabel="No public link templates found."
        onCreate={(template: PortableLinkTemplate) =>
          LinkTemplatesService.createLinkTemplateApiV1LinkTemplatesPost({
            requestBody: template as LinkTemplateCreate,
          })
        }
        onUpdate={(templateId: number, template: Partial<PortableLinkTemplate>) =>
          LinkTemplatesService.updateLinkTemplateApiV1LinkTemplatesTemplateIdPatch({
            templateId,
            requestBody: template as LinkTemplateUpdate,
          })
        }
        onDelete={(templateId: number) =>
          LinkTemplatesService.deleteLinkTemplateApiV1LinkTemplatesTemplateIdDelete({ templateId })
        }
        onImport={(payload: unknown) =>
          LinkTemplatesService.importLinkTemplatesApiV1LinkTemplatesImportPost({
            requestBody: payload,
          })
        }
        onExport={(templateIds: number[]) =>
          LinkTemplatesService.exportLinkTemplatesApiV1LinkTemplatesExportPost({
            requestBody: { template_ids: templateIds },
          })
        }
        onChanged={invalidateTemplates}
      />
    </AdminPageLayout>
  );
}

export default AdminLinkTemplates;
