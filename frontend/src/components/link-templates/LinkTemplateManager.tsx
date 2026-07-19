import React from "react";
import { Button } from "@/components/buttons/Button";
import { IconButton } from "@/components/buttons/IconButton";
import { Table } from "@/components/data-display/Table";
import { TextField } from "@/components/forms/TextField";
import { DropdownMenu } from "@/components/overlays/DropdownMenu";
import { FormDrawer } from "@/components/overlays";
import { useToast } from "@/contexts/ToastContext";
import {
  FALLBACK_LINK_TEMPLATE_ICON,
  getAvailableIconNames,
  getIconComponent,
  normalizeLinkTemplateIconName,
} from "@/utils/iconMapping";
import type { LinkTemplateExportBundle } from "@/types/generated/models/LinkTemplateExportBundle";
import type { PortableLinkTemplate } from "@/types/generated/models/PortableLinkTemplate";
import { ApiError } from "@/types/generated/core/ApiError";
import { Checkbox, Switch, ToggleGroup } from "@tidemark-security/ux";
import {
  Download,
  Edit2,
  FileUp,
  MoreHorizontal,
  Plus,
  Trash2,
} from "lucide-react";

type SurfaceScope = "entity" | "timeline_item";
type TemplateEntityType = "alert" | "case" | "task";

export type ManagedLinkTemplate = PortableLinkTemplate & {
  id: number;
  created_at?: string;
  updated_at?: string;
  user_id?: string;
};

type TemplateDraft = {
  template_id: string;
  name: string;
  icon_name: string;
  tooltip_template: string;
  url_template: string;
  field_names: string[];
  conditions: Record<string, unknown> | null;
  surface_scopes: SurfaceScope[];
  entity_types: TemplateEntityType[];
  enabled: boolean;
  display_order: number;
};

export interface LinkTemplateManagerProps<TTemplate extends ManagedLinkTemplate> {
  title?: string;
  description?: string;
  headerIcon?: React.ReactNode;
  headerVariant?: "default" | "settings-card";
  templates: TTemplate[];
  isLoading?: boolean;
  createLabel?: string;
  emptyLabel?: string;
  onCreate: (template: PortableLinkTemplate) => Promise<unknown>;
  onUpdate: (templateId: number, template: Partial<PortableLinkTemplate>) => Promise<unknown>;
  onDelete: (templateId: number) => Promise<unknown>;
  onImport: (payload: unknown) => Promise<TTemplate[]>;
  onExport: (templateIds: number[]) => Promise<LinkTemplateExportBundle>;
  onChanged: () => void;
}

const EMPTY_DRAFT: TemplateDraft = {
  template_id: "",
  name: "",
  icon_name: FALLBACK_LINK_TEMPLATE_ICON,
  tooltip_template: "",
  url_template: "",
  field_names: [],
  conditions: null,
  surface_scopes: ["timeline_item"],
  entity_types: [],
  enabled: true,
  display_order: 100,
};

const SURFACE_OPTIONS: Array<{ value: SurfaceScope; label: string }> = [
  { value: "timeline_item", label: "Timeline items" },
  { value: "entity", label: "Parent entity" },
];

const ENTITY_OPTIONS: Array<{ value: TemplateEntityType; label: string }> = [
  { value: "alert", label: "Alerts" },
  { value: "case", label: "Cases" },
  { value: "task", label: "Tasks" },
];

function valuesToCsv(values: string[] | null | undefined): string {
  return values?.join(", ") || "";
}

function csvToValues(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.body && typeof error.body === "object" && "detail" in error.body) {
      const detail = (error.body as { detail?: unknown }).detail;
      if (typeof detail === "string") {
        return detail;
      }
      if (
        detail &&
        typeof detail === "object" &&
        "message" in detail &&
        typeof (detail as { message?: unknown }).message === "string"
      ) {
        return (detail as { message: string }).message;
      }
    }
    if (error.body && typeof error.body === "object" && "message" in error.body) {
      const message = (error.body as { message?: unknown }).message;
      if (typeof message === "string") {
        return message;
      }
    }
  }
  if (error instanceof Error) return error.message;
  return fallback;
}

function toDraft(template?: ManagedLinkTemplate): TemplateDraft {
  if (!template) return { ...EMPTY_DRAFT };
  const surface = template.surface_scopes?.includes("entity") ? "entity" : "timeline_item";
  return {
    template_id: template.template_id,
    name: template.name,
    icon_name: normalizeLinkTemplateIconName(template.icon_name),
    tooltip_template: template.tooltip_template,
    url_template: template.url_template,
    field_names: template.field_names || [],
    conditions: template.conditions || null,
    surface_scopes: [surface],
    entity_types: (template.entity_types || []) as TemplateEntityType[],
    enabled: template.enabled ?? true,
    display_order: template.display_order ?? 100,
  };
}

function formatScopes(template: ManagedLinkTemplate): string {
  const surfaces = template.surface_scopes?.length ? template.surface_scopes : ["timeline_item"];
  const entityTypes = template.entity_types?.length ? template.entity_types.join(", ") : "all entities";
  const surfaceLabel = surfaces.includes("entity") ? "parent" : "timeline";
  return `${surfaceLabel}; ${entityTypes}`;
}

function toggleValue<T extends string>(values: T[], value: T, checked: boolean): T[] {
  if (checked) {
    return values.includes(value) ? values : [...values, value];
  }
  return values.filter((item) => item !== value);
}

function buildPayload(draft: TemplateDraft, conditionsInput: string): PortableLinkTemplate | null {
  if (!draft.template_id.trim() || !draft.name.trim() || !draft.tooltip_template.trim() || !draft.url_template.trim()) {
    return null;
  }
  if (draft.surface_scopes.length !== 1) {
    return null;
  }

  let conditions: Record<string, unknown> | null = null;
  if (conditionsInput.trim()) {
    const parsed = JSON.parse(conditionsInput);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
      throw new Error("Conditions must be a JSON object");
    }
    conditions = parsed as Record<string, unknown>;
  }

  return {
    template_id: draft.template_id.trim(),
    name: draft.name.trim(),
    icon_name: normalizeLinkTemplateIconName(draft.icon_name.trim()),
    tooltip_template: draft.tooltip_template,
    url_template: draft.url_template,
    field_names: draft.field_names.length > 0 ? draft.field_names : null,
    conditions,
    surface_scopes: draft.surface_scopes,
    entity_types: draft.entity_types.length > 0 ? draft.entity_types : null,
    enabled: draft.enabled,
    display_order: draft.display_order,
  };
}

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function LinkTemplateManager<TTemplate extends ManagedLinkTemplate>({
  title,
  description,
  templates,
  isLoading = false,
  createLabel = "Add Template",
  emptyLabel = "No link templates found.",
  onCreate,
  onUpdate,
  onDelete,
  onImport,
  onExport,
  onChanged,
  headerIcon,
  headerVariant = "default",
}: LinkTemplateManagerProps<TTemplate>) {
  const { showToast } = useToast();
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const iconDropdownRef = React.useRef<HTMLDivElement>(null);
  const [isModalOpen, setIsModalOpen] = React.useState(false);
  const [editingTemplate, setEditingTemplate] = React.useState<TTemplate | null>(null);
  const [draft, setDraft] = React.useState<TemplateDraft>(EMPTY_DRAFT);
  const [fieldNamesInput, setFieldNamesInput] = React.useState("");
  const [conditionsInput, setConditionsInput] = React.useState("");
  const [iconSearchTerm, setIconSearchTerm] = React.useState("");
  const [showIconDropdown, setShowIconDropdown] = React.useState(false);
  const [pendingAction, setPendingAction] = React.useState<string | null>(null);

  const allIconNames = React.useMemo(() => getAvailableIconNames(), []);
  const filteredIcons = React.useMemo(
    () => allIconNames.filter((name) => name.toLowerCase().includes(iconSearchTerm.toLowerCase())),
    [allIconNames, iconSearchTerm],
  );

  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (iconDropdownRef.current && !iconDropdownRef.current.contains(event.target as Node)) {
        setShowIconDropdown(false);
        setIconSearchTerm("");
      }
    };

    if (showIconDropdown) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showIconDropdown]);

  const sortedTemplates = React.useMemo(
    () => [...templates].sort((a, b) => (a.display_order ?? 100) - (b.display_order ?? 100) || a.name.localeCompare(b.name)),
    [templates],
  );

  const openCreateModal = () => {
    setEditingTemplate(null);
    setDraft({ ...EMPTY_DRAFT });
    setFieldNamesInput("");
    setConditionsInput("");
    setShowIconDropdown(false);
    setIconSearchTerm("");
    setIsModalOpen(true);
  };

  const openEditModal = (template: TTemplate) => {
    const nextDraft = toDraft(template);
    setEditingTemplate(template);
    setDraft(nextDraft);
    setFieldNamesInput(valuesToCsv(nextDraft.field_names));
    setConditionsInput(nextDraft.conditions ? JSON.stringify(nextDraft.conditions, null, 2) : "");
    setShowIconDropdown(false);
    setIconSearchTerm("");
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingTemplate(null);
    setDraft({ ...EMPTY_DRAFT });
    setFieldNamesInput("");
    setConditionsInput("");
    setShowIconDropdown(false);
    setIconSearchTerm("");
  };

  const submitForm = async () => {
    try {
      const payload = buildPayload({ ...draft, field_names: csvToValues(fieldNamesInput) }, conditionsInput);
      if (!payload) {
        showToast("Validation Error", "Template ID, name, tooltip, URL, and one surface are required", "error");
        return;
      }

      setPendingAction("save");
      if (editingTemplate) {
        const { template_id: _templateId, ...updatePayload } = payload;
        await onUpdate(editingTemplate.id, updatePayload);
        showToast("Saved", "Link template updated", "success");
      } else {
        await onCreate(payload);
        showToast("Created", "Link template created", "success");
      }
      onChanged();
      closeModal();
    } catch (error) {
      showToast("Error", getErrorMessage(error, "Failed to save link template"), "error");
    } finally {
      setPendingAction(null);
    }
  };

  const handleToggleEnabled = async (template: TTemplate, checked: boolean) => {
    try {
      setPendingAction(`toggle-${template.id}`);
      await onUpdate(template.id, { enabled: checked });
      onChanged();
    } catch (error) {
      showToast("Error", getErrorMessage(error, "Failed to update link template"), "error");
    } finally {
      setPendingAction(null);
    }
  };

  const handleDelete = async (template: TTemplate) => {
    if (!window.confirm(`Delete ${template.name}?`)) return;
    try {
      setPendingAction(`delete-${template.id}`);
      await onDelete(template.id);
      onChanged();
      showToast("Deleted", "Link template deleted", "success");
    } catch (error) {
      showToast("Error", getErrorMessage(error, "Failed to delete link template"), "error");
    } finally {
      setPendingAction(null);
    }
  };

  const handleExport = async (template: TTemplate) => {
    try {
      setPendingAction(`export-${template.id}`);
      const bundle = await onExport([template.id]);
      downloadJson(`${template.template_id}.link-template.json`, bundle);
      showToast("Exported", "Link template JSON downloaded", "success");
    } catch (error) {
      showToast("Error", getErrorMessage(error, "Failed to export link template"), "error");
    } finally {
      setPendingAction(null);
    }
  };

  const handleImportFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    try {
      setPendingAction("import");
      const text = await file.text();
      const payload = JSON.parse(text);
      const imported = await onImport(payload);
      onChanged();
      showToast("Imported", `${imported.length} link template${imported.length === 1 ? "" : "s"} imported`, "success");
    } catch (error) {
      showToast("Error", getErrorMessage(error, "Failed to import link templates"), "error");
    } finally {
      setPendingAction(null);
    }
  };

  const setDraftValue = <K extends keyof TemplateDraft>(key: K, value: TemplateDraft[K]) => {
    setDraft((previous) => ({ ...previous, [key]: value }));
  };

  const actionButtons = (
    <div className="flex flex-none items-center gap-2">
      <Button
        variant="neutral-secondary"
        icon={<FileUp />}
        disabled={pendingAction === "import"}
        onClick={() => fileInputRef.current?.click()}
      >
        Import
      </Button>
      <Button icon={<Plus />} onClick={openCreateModal}>
        {createLabel}
      </Button>
    </div>
  );

  return (
    <div className="flex w-full flex-col items-start gap-6">
      <input
        ref={fileInputRef}
        type="file"
        accept="application/json,.json"
        className="hidden"
        onChange={handleImportFile}
      />

      {headerVariant === "settings-card" && title ? (
        <>
          <div className="flex w-full flex-wrap items-center gap-3 border-b border-neutral-border pb-4">
            <div className="flex min-w-0 flex-1 items-center gap-2">
              {headerIcon}
              <h3 className="text-heading-3 font-heading-3 text-default-font">
                {title}
              </h3>
            </div>
            {actionButtons}
          </div>
          {description ? (
            <span className="text-body font-body text-subtext-color">
              {description}
            </span>
          ) : null}
        </>
      ) : (title || description) ? (
        <div className="flex w-full flex-wrap items-start gap-3">
          <div className="flex min-w-0 grow shrink basis-0 flex-col gap-1">
            {title ? (
              <span className="text-heading-2 font-heading-2 text-default-font">{title}</span>
            ) : null}
            {description ? (
              <span className="text-body font-body text-subtext-color">{description}</span>
            ) : null}
          </div>
          {actionButtons}
        </div>
      ) : (
        <div className="flex w-full justify-end">
          {actionButtons}
        </div>
      )}

      {isLoading ? (
        <div className="flex w-full items-center justify-center py-12">
          <span className="text-body font-body text-subtext-color">Loading templates...</span>
        </div>
      ) : sortedTemplates.length === 0 ? (
        <div className="flex w-full items-center justify-center py-12">
          <span className="text-body font-body text-subtext-color">{emptyLabel}</span>
        </div>
      ) : (
        <div className="flex w-full flex-col overflow-auto">
          <Table
            header={
              <Table.HeaderRow>
                <Table.HeaderCell>Template</Table.HeaderCell>
                <Table.HeaderCell>Scope</Table.HeaderCell>
                <Table.HeaderCell>URL Template</Table.HeaderCell>
                <Table.HeaderCell>Fields</Table.HeaderCell>
                <Table.HeaderCell>Order</Table.HeaderCell>
                <Table.HeaderCell>Enabled</Table.HeaderCell>
                <Table.HeaderCell />
              </Table.HeaderRow>
            }
          >
            {sortedTemplates.map((template) => (
              <Table.Row key={template.id}>
                <Table.Cell>
                  <div className="flex items-center gap-3">
                    <span className="text-[20px] text-neutral-700">
                      {getIconComponent(template.icon_name)}
                    </span>
                    <div className="flex min-w-0 flex-col gap-1">
                      <span className="truncate text-body-bold font-body-bold text-default-font">
                        {template.name}
                      </span>
                      <span className="truncate text-caption font-caption text-neutral-500">
                        {template.template_id}
                      </span>
                    </div>
                  </div>
                </Table.Cell>
                <Table.Cell>
                  <span className="text-caption font-caption text-neutral-500">
                    {formatScopes(template)}
                  </span>
                </Table.Cell>
                <Table.Cell>
                  <span className="block max-w-sm truncate font-monospace-body text-monospace-body text-neutral-700">
                    {template.url_template}
                  </span>
                </Table.Cell>
                <Table.Cell>
                  <span className="text-caption font-caption text-neutral-500">
                    {template.field_names?.join(", ") || "-"}
                  </span>
                </Table.Cell>
                <Table.Cell>
                  <span className="text-body font-body text-neutral-500">
                    {template.display_order ?? 0}
                  </span>
                </Table.Cell>
                <Table.Cell>
                  <Switch
                    checked={template.enabled ?? true}
                    disabled={pendingAction === `toggle-${template.id}`}
                    onCheckedChange={(checked) => handleToggleEnabled(template, Boolean(checked))}
                  />
                </Table.Cell>
                <Table.Cell>
                  <div className="flex justify-end">
                    <DropdownMenu.Root>
                      <DropdownMenu.Trigger asChild>
                        <IconButton icon={<MoreHorizontal />} aria-label={`Actions for ${template.name}`} />
                      </DropdownMenu.Trigger>
                      <DropdownMenu.Content side="bottom" align="end" sideOffset={8}>
                        <DropdownMenu.DropdownItem
                          icon={<Edit2 />}
                          label="Edit"
                          onClick={() => openEditModal(template)}
                        />
                        <DropdownMenu.DropdownItem
                          icon={<Download />}
                          label="Export"
                          onClick={() => handleExport(template)}
                        />
                        <DropdownMenu.DropdownDivider />
                        <DropdownMenu.DropdownItem
                          icon={<Trash2 />}
                          label="Delete"
                          onClick={() => handleDelete(template)}
                        />
                      </DropdownMenu.Content>
                    </DropdownMenu.Root>
                  </div>
                </Table.Cell>
              </Table.Row>
            ))}
          </Table>
        </div>
      )}

      <FormDrawer
        open={isModalOpen}
        title={editingTemplate ? "Edit Link Template" : "Create Link Template"}
        description="Set fields and scope"
        widthClassName="w-[720px]"
        closeLabel="Close link template drawer"
        onOpenChange={(open) => {
          if (!open) closeModal();
        }}
        footer={
          <div className="flex w-full items-center gap-2">
            <Button className="flex-1" variant="neutral-secondary" onClick={closeModal} disabled={pendingAction === "save"}>
              Cancel
            </Button>
            <Button className="flex-1" onClick={submitForm} loading={pendingAction === "save"}>
              {editingTemplate ? "Save Changes" : "Create Template"}
            </Button>
          </div>
        }
      >
        {isModalOpen ? (
          <>
            <div className="flex w-full items-center gap-2">
              <div className="flex grow shrink-0 basis-0 flex-col items-start gap-1">
                <span className="text-body-bold font-body-bold text-default-font">
                  {draft.template_id || "New template"}
                </span>
                <span className="text-caption font-caption text-subtext-color">
                  {draft.surface_scopes[0] === "entity" ? "Parent entity" : "Timeline items"}
                </span>
              </div>
              <span className="text-[24px] text-brand-primary">
                {getIconComponent(draft.icon_name)}
              </span>
            </div>

            <div className="grid w-full grid-cols-1 gap-4 tablet:grid-cols-2">
              <TextField className="h-auto w-full flex-none" label="Template ID">
                <TextField.Input
                  placeholder="virustotal-domain"
                  value={draft.template_id}
                  disabled={Boolean(editingTemplate)}
                  onChange={(event) => setDraftValue("template_id", event.target.value)}
                />
              </TextField>

              <TextField className="h-auto w-full flex-none" label="Name">
                <TextField.Input
                  placeholder="VirusTotal Domain Lookup"
                  value={draft.name}
                  onChange={(event) => setDraftValue("name", event.target.value)}
                />
              </TextField>

              <div className="flex w-full flex-col gap-2 tablet:col-span-2">
                <label className="text-body-bold font-body-bold text-default-font">Icon</label>
                <div className="relative" ref={iconDropdownRef}>
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 rounded-md border border-solid border-neutral-border bg-default-background px-3 py-2 text-left hover:border-neutral-400"
                    onClick={() => setShowIconDropdown((value) => !value)}
                  >
                    <span className="text-[20px] text-neutral-700">{getIconComponent(draft.icon_name)}</span>
                    <span className="flex-1 text-body font-body text-default-font">{draft.icon_name}</span>
                  </button>

                  {showIconDropdown ? (
                    <div className="absolute z-10 mt-1 w-full rounded-md border border-solid border-neutral-border bg-default-background shadow-lg">
                      <div className="p-2">
                        <TextField className="h-auto w-full">
                          <TextField.Input
                            placeholder="Search icons..."
                            value={iconSearchTerm}
                            onChange={(event) => setIconSearchTerm(event.target.value)}
                            onClick={(event) => event.stopPropagation()}
                          />
                        </TextField>
                      </div>
                      <div className="max-h-64 overflow-y-auto">
                        {filteredIcons.map((iconName) => (
                          <button
                            key={iconName}
                            type="button"
                            className="flex w-full items-center gap-3 px-4 py-2 text-left hover:bg-neutral-100"
                            onClick={() => {
                              setDraftValue("icon_name", iconName);
                              setShowIconDropdown(false);
                              setIconSearchTerm("");
                            }}
                          >
                            <span className="text-[20px] text-neutral-700">{getIconComponent(iconName)}</span>
                            <span className="text-body font-body text-default-font">{iconName}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>

              <TextField className="h-auto w-full flex-none tablet:col-span-2" label="Tooltip Template">
                <TextField.Input
                  placeholder="Open {{observable_value}}"
                  value={draft.tooltip_template}
                  onChange={(event) => setDraftValue("tooltip_template", event.target.value)}
                />
              </TextField>

              <TextField className="h-auto w-full flex-none tablet:col-span-2" label="URL Template">
                <TextField.Input
                  placeholder="https://example.com/search?q={{observable_value}}"
                  value={draft.url_template}
                  onChange={(event) => setDraftValue("url_template", event.target.value)}
                />
              </TextField>

              <TextField className="h-auto w-full flex-none" label="Field Names">
                <TextField.Input
                  placeholder="observable_value, domain"
                  value={fieldNamesInput}
                  onChange={(event) => setFieldNamesInput(event.target.value)}
                />
              </TextField>

              <TextField className="h-auto w-full flex-none" label="Display Order">
                <TextField.Input
                  type="number"
                  value={String(draft.display_order)}
                  onChange={(event) => setDraftValue("display_order", Number(event.target.value) || 0)}
                />
              </TextField>

              <div className="flex w-full flex-col gap-2 tablet:col-span-2">
                <span className="text-body-bold font-body-bold text-default-font">Surface</span>
                <ToggleGroup
                  className="h-auto w-full"
                  value={draft.surface_scopes[0] || "timeline_item"}
                  onValueChange={(value) => {
                    if (value) setDraftValue("surface_scopes", [value as SurfaceScope]);
                  }}
                >
                  {SURFACE_OPTIONS.map((option) => (
                    <ToggleGroup.Item key={option.value} className="flex-1" icon={null} value={option.value}>
                      {option.label}
                    </ToggleGroup.Item>
                  ))}
                </ToggleGroup>
              </div>

              <div className="flex w-full flex-col gap-2 tablet:col-span-2">
                <span className="text-body-bold font-body-bold text-default-font">Entity Types</span>
                <div className="grid gap-2 rounded-md border border-neutral-border bg-neutral-50 px-3 py-3 tablet:grid-cols-3">
                  {ENTITY_OPTIONS.map((option) => (
                    <label key={option.value} className="flex items-center gap-2 text-body font-body text-default-font">
                      <Checkbox
                        checked={draft.entity_types.includes(option.value)}
                        onCheckedChange={(checked) =>
                          setDraftValue("entity_types", toggleValue(draft.entity_types, option.value, Boolean(checked)))
                        }
                        size="small"
                      />
                      {option.label}
                    </label>
                  ))}
                  <span className="text-caption font-caption text-subtext-color tablet:col-span-3">
                    Leave empty to match all entity types.
                  </span>
                </div>
              </div>

              <div className="flex w-full flex-col gap-2 tablet:col-span-2">
                <label className="text-body-bold font-body-bold text-default-font">Conditions JSON</label>
                <textarea
                  aria-label="Conditions JSON"
                  className="min-h-24 w-full rounded-md border border-solid border-neutral-border bg-default-background px-3 py-2 font-monospace-body text-monospace-body text-default-font"
                  value={conditionsInput}
                  onChange={(event) => setConditionsInput(event.target.value)}
                />
                <span className="text-caption font-caption text-subtext-color">
                  Must be a JSON object. Example: {`{"observable_type": "DOMAIN"}`}
                </span>
              </div>

              <div className="flex w-full items-center justify-between gap-4 rounded-md border border-neutral-border bg-neutral-50 px-3 py-3 tablet:col-span-2">
                <div className="flex flex-col gap-1">
                  <span className="text-body-bold font-body-bold text-default-font">Enabled</span>
                  <span className="text-caption font-caption text-subtext-color">Disabled templates are hidden from resolved link buttons.</span>
                </div>
                <Switch checked={draft.enabled} onCheckedChange={(checked) => setDraftValue("enabled", Boolean(checked))} />
              </div>
            </div>
          </>
        ) : null}
      </FormDrawer>
    </div>
  );
}
