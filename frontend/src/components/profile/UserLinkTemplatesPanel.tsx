import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/buttons/Button";
import { DropdownMenu } from "@/components/overlays/DropdownMenu";
import { IconButton } from "@/components/buttons/IconButton";
import { IconWithBackground } from "@/components/misc/IconWithBackground";
import { ModalShell } from "@/components/overlays";
import { Switch } from "@/components/forms/Switch";
import { Table } from "@/components/data-display/Table";
import { TextField } from "@/components/forms/TextField";
import { useToast } from "@/contexts/ToastContext";
import {
  resolvedLinkTemplateQueryKey,
  userLinkTemplatePreferenceQueryKey,
  useUserLinkTemplatePreferences,
} from "@/hooks/useUserLinkTemplates";
import { UserLinkTemplatesService } from "@/services/userLinkTemplatesService";
import { LinkTemplatesService } from "@/types/generated/services/LinkTemplatesService";
import type { LinkTemplateRead } from "@/types/generated/models/LinkTemplateRead";
import type { UserLinkTemplatePreferenceRead } from "@/types/userLinkTemplates";
import { getIconComponent } from "@/utils/iconMapping";
import {
  Edit2,
  ExternalLink,
  MoreHorizontal,
  RotateCcw,
} from "lucide-react";

const USER_PLACEHOLDER_PATTERN = /\{\{\s*user\.([A-Za-z0-9_.-]+)\s*\}\}/g;

function extractUserValueKeys(template: LinkTemplateRead): string[] {
  const keys = new Set<string>();
  const scan = (value: string) => {
    for (const match of value.matchAll(USER_PLACEHOLDER_PATTERN)) {
      keys.add(match[1]);
    }
  };
  scan(template.url_template);
  scan(template.tooltip_template);
  return [...keys].sort();
}

function formatValueSummary(values: Record<string, string>, keys: string[]): string {
  if (keys.length === 0) return "No user values required";
  const filled = keys.filter((key) => values[key]?.trim()).length;
  return `${filled}/${keys.length} values set`;
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error) return error.message;
  return fallback;
}

export function UserLinkTemplatesPanel() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [isModalOpen, setIsModalOpen] = React.useState(false);
  const [editingTemplate, setEditingTemplate] = React.useState<LinkTemplateRead | null>(null);
  const [editingPreference, setEditingPreference] =
    React.useState<UserLinkTemplatePreferenceRead | null>(null);
  const [enabled, setEnabled] = React.useState(true);
  const [values, setValues] = React.useState<Record<string, string>>({});

  const { data: templates = [], isLoading: isLoadingTemplates } = useQuery({
    queryKey: ["user-configurable-link-templates"],
    queryFn: () =>
      LinkTemplatesService.getLinkTemplatesApiV1LinkTemplatesGet({
        enabledOnly: true,
      }),
    staleTime: 5 * 60 * 1000,
  });
  const { data: preferences = [], isLoading: isLoadingPreferences } =
    useUserLinkTemplatePreferences();

  const preferenceByTemplateId = React.useMemo(() => {
    return new Map(preferences.map((preference) => [preference.template_id, preference]));
  }, [preferences]);

  const invalidateLinks = () => {
    queryClient.invalidateQueries({ queryKey: userLinkTemplatePreferenceQueryKey });
    queryClient.invalidateQueries({ queryKey: resolvedLinkTemplateQueryKey });
  };

  const upsertMutation = useMutation({
    mutationFn: ({
      templateId,
      requestBody,
    }: {
      templateId: number;
      requestBody: { enabled: boolean; values: Record<string, string> };
    }) =>
      UserLinkTemplatesService.upsertUserLinkTemplatePreference({
        templateId,
        requestBody,
      }),
    onSuccess: () => {
      invalidateLinks();
      closeModal();
      showToast("Saved", "Deep link preference updated", "success");
    },
    onError: (error) => {
      showToast("Error", getErrorMessage(error, "Failed to update deep link preference"), "error");
    },
  });

  const resetMutation = useMutation({
    mutationFn: (templateId: number) =>
      UserLinkTemplatesService.deleteUserLinkTemplatePreference({ templateId }),
    onSuccess: () => {
      invalidateLinks();
      showToast("Reset", "Deep link preference reset", "success");
    },
    onError: (error) => {
      showToast("Error", getErrorMessage(error, "Failed to reset deep link preference"), "error");
    },
  });

  const openEditModal = (template: LinkTemplateRead) => {
    const preference = preferenceByTemplateId.get(template.id) || null;
    const keys = extractUserValueKeys(template);
    const nextValues = { ...(preference?.values || {}) };
    keys.forEach((key) => {
      nextValues[key] = nextValues[key] || "";
    });

    setEditingTemplate(template);
    setEditingPreference(preference);
    setEnabled(preference?.enabled ?? true);
    setValues(nextValues);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingTemplate(null);
    setEditingPreference(null);
    setEnabled(true);
    setValues({});
  };

  const submitForm = () => {
    if (!editingTemplate) return;

    upsertMutation.mutate({
      templateId: editingTemplate.id,
      requestBody: {
        enabled,
        values,
      },
    });
  };

  const sortedTemplates = [...templates].sort(
    (a, b) => (a.display_order ?? 100) - (b.display_order ?? 100),
  );
  const isLoading = isLoadingTemplates || isLoadingPreferences;
  const isSaving = upsertMutation.isPending;
  const userValueKeys = editingTemplate ? extractUserValueKeys(editingTemplate) : [];

  return (
    <div className="flex w-full flex-col items-start gap-6 rounded-md border border-solid border-neutral-border bg-neutral-50 px-6 py-6">
      <div className="flex w-full flex-wrap items-center gap-2">
        <IconWithBackground variant="neutral" size="medium" icon={<ExternalLink />} />
        <span className="grow shrink-0 basis-0 text-heading-2 font-heading-2 text-default-font">
          Deep Links
        </span>
      </div>

      <span className="text-body font-body text-subtext-color">
        Configure your values and visibility for available contextual action links.
      </span>

      {isLoading ? (
        <span className="text-body font-body text-subtext-color">Loading deep links...</span>
      ) : sortedTemplates.length === 0 ? (
        <span className="text-body font-body text-subtext-color">
          No deep link templates are available.
        </span>
      ) : (
        <div className="flex w-full flex-col overflow-auto">
          <Table
            header={
              <Table.HeaderRow>
                <Table.HeaderCell>Template</Table.HeaderCell>
                <Table.HeaderCell>User Values</Table.HeaderCell>
                <Table.HeaderCell>URL Template</Table.HeaderCell>
                <Table.HeaderCell>Enabled</Table.HeaderCell>
                <Table.HeaderCell />
              </Table.HeaderRow>
            }
          >
            {sortedTemplates.map((template) => {
              const preference = preferenceByTemplateId.get(template.id);
              const keys = extractUserValueKeys(template);
              const rowEnabled = preference?.enabled ?? true;

              return (
                <Table.Row key={template.id}>
                  <Table.Cell>
                    <div className="flex items-center gap-3">
                      <span className="text-[20px] text-neutral-700">
                        {getIconComponent(template.icon_name)}
                      </span>
                      <div className="flex flex-col gap-1">
                        <span className="text-body-bold font-body-bold text-default-font">
                          {template.name}
                        </span>
                        <span className="text-caption font-caption text-neutral-500">
                          {template.template_id}
                        </span>
                      </div>
                    </div>
                  </Table.Cell>
                  <Table.Cell>
                    <span className="text-caption font-caption text-neutral-500">
                      {formatValueSummary(preference?.values || {}, keys)}
                    </span>
                  </Table.Cell>
                  <Table.Cell>
                    <span className="block max-w-sm truncate font-monospace-body text-monospace-body text-neutral-700">
                      {template.url_template}
                    </span>
                  </Table.Cell>
                  <Table.Cell>
                    <Switch
                      checked={rowEnabled}
                      onCheckedChange={(checked) =>
                        upsertMutation.mutate({
                          templateId: template.id,
                          requestBody: {
                            enabled: checked,
                            values: preference?.values || {},
                          },
                        })
                      }
                    />
                  </Table.Cell>
                  <Table.Cell>
                    <div className="flex justify-end">
                      <DropdownMenu.Root>
                        <DropdownMenu.Trigger asChild>
                          <IconButton icon={<MoreHorizontal />} />
                        </DropdownMenu.Trigger>
                        <DropdownMenu.Content side="bottom" align="end" sideOffset={8}>
                          <DropdownMenu.DropdownItem
                            icon={<Edit2 />}
                            label="Configure"
                            onClick={() => openEditModal(template)}
                          />
                          {preference ? (
                            <>
                              <DropdownMenu.DropdownDivider />
                              <DropdownMenu.DropdownItem
                                icon={<RotateCcw />}
                                label="Reset"
                                onClick={() => resetMutation.mutate(template.id)}
                              />
                            </>
                          ) : null}
                        </DropdownMenu.Content>
                      </DropdownMenu.Root>
                    </div>
                  </Table.Cell>
                </Table.Row>
              );
            })}
          </Table>
        </div>
      )}

      {isModalOpen && editingTemplate ? (
        <ModalShell
          title="Configure Deep Link"
          description="Set your values for this link template"
          panelClassName="max-w-2xl max-h-[90vh] overflow-y-auto"
          onClose={closeModal}
        >
          <div className="flex w-full items-center gap-2">
            <div className="flex grow shrink-0 basis-0 flex-col items-start gap-1">
              <span className="text-heading-2 font-heading-2 text-default-font">
                {editingTemplate.name}
              </span>
              <span className="text-body font-body text-subtext-color">
                {editingTemplate.template_id}
              </span>
            </div>
            <span className="text-[24px] text-brand-primary">
              {getIconComponent(editingTemplate.icon_name)}
            </span>
          </div>

          <div className="flex w-full items-start rounded-md border border-solid border-neutral-border bg-default-background">
            <div className="flex grow shrink-0 basis-0 flex-col items-start gap-4 px-4 py-4">
              <div className="flex w-full items-center justify-between gap-4">
                <div className="flex flex-col gap-1">
                  <span className="text-body-bold font-body-bold text-default-font">Enabled</span>
                  <span className="text-caption font-caption text-subtext-color">
                    Disabled links are hidden for your account.
                  </span>
                </div>
                <Switch checked={enabled} onCheckedChange={setEnabled} />
              </div>

              {userValueKeys.length > 0 ? (
                <div className="flex w-full flex-col gap-4">
                  {userValueKeys.map((key) => (
                    <TextField key={key} className="h-auto w-full flex-none" label={key}>
                      <TextField.Input
                        value={values[key] || ""}
                        onChange={(event) =>
                          setValues((previous) => ({
                            ...previous,
                            [key]: event.target.value,
                          }))
                        }
                      />
                    </TextField>
                  ))}
                </div>
              ) : (
                <span className="text-body font-body text-subtext-color">
                  This template does not require user-specific values.
                </span>
              )}

              <div className="flex w-full flex-col gap-2">
                <span className="text-caption-bold font-caption-bold text-default-font">
                  URL Template
                </span>
                <span className="break-all rounded-md border border-solid border-neutral-border bg-neutral-50 px-3 py-2 font-monospace-body text-monospace-body text-subtext-color">
                  {editingTemplate.url_template}
                </span>
              </div>
            </div>
          </div>

          <div className="flex w-full items-center justify-end gap-2">
            <Button variant="neutral-secondary" onClick={closeModal} disabled={isSaving}>
              Cancel
            </Button>
            <Button onClick={submitForm} loading={isSaving}>
              Save Preference
            </Button>
          </div>
        </ModalShell>
      ) : null}
    </div>
  );
}
