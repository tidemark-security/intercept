import React, { useState, useEffect, useRef } from "react";
import { Badge } from "@/components/data-display/Badge";
import { Button } from "@/components/buttons/Button";
import { DropdownMenu } from "@/components/overlays/DropdownMenu";
import { IconButton } from "@/components/buttons/IconButton";
import { ModalShell } from "@/components/overlays";
import { Table } from "@/components/data-display/Table";
import { TextField } from "@/components/forms/TextField";
import { Toast } from "@/components/feedback/Toast";
import { Switch } from "@/components/forms/Switch";
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";
import { AdminPageLayout } from "../components/layout/AdminPageLayout";
import { LinkTemplatesService } from "../types/generated/services/LinkTemplatesService";
import type { LinkTemplateRead, LinkTemplateCreate, LinkTemplateUpdate } from "../types/generated";
import { ApiError } from "../types/generated";
import { useSession } from "../contexts/sessionContext";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "@/components/navigation/Link";
import { getIconComponent, getAvailableIconNames } from "../utils/iconMapping";

import { AlertCircle, ArrowLeft, CheckCircle, ChevronDown, Edit, Link2, MoreHorizontal, Plus, Trash2 } from 'lucide-react';
interface FormData {
  template_id: string;
  name: string;
  icon_name: string;
  tooltip_template: string;
  url_template: string;
  field_names: string[];
  conditions: Record<string, any> | null;
  enabled: boolean;
  display_order: number;
}

const emptyFormData: FormData = {
  template_id: "",
  name: "",
  icon_name: "FeatherLink",
  tooltip_template: "",
  url_template: "",
  field_names: [],
  conditions: null,
  enabled: true,
  display_order: 100,
};

function AdminLinkTemplates() {
  const { user: currentUser } = useSession();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [formData, setFormData] = useState<FormData>(emptyFormData);
  const [fieldNamesInput, setFieldNamesInput] = useState("");
  const [conditionsInput, setConditionsInput] = useState("");
  const [iconSearchTerm, setIconSearchTerm] = useState("");
  const [showIconDropdown, setShowIconDropdown] = useState(false);
  const iconDropdownRef = useRef<HTMLDivElement>(null);

  const isAdmin = currentUser?.role === "ADMIN";

  // Get all available icons
  const allIconNames = getAvailableIconNames();
  
  // Filter icons based on search term
  const filteredIcons = allIconNames.filter((name) =>
    name.toLowerCase().includes(iconSearchTerm.toLowerCase())
  );

  // Close icon dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (iconDropdownRef.current && !iconDropdownRef.current.contains(event.target as Node)) {
        setShowIconDropdown(false);
        setIconSearchTerm("");
      }
    };

    if (showIconDropdown) {
      document.addEventListener("mousedown", handleClickOutside);
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showIconDropdown]);

  // Fetch templates
  const { data: templates, isLoading } = useQuery({
    queryKey: ["admin-link-templates"],
    queryFn: async () => {
      return await LinkTemplatesService.getLinkTemplatesApiV1LinkTemplatesGet({
        enabledOnly: false,
      });
    },
    enabled: isAdmin,
  });

  // Create mutation
  const createMutation = useMutation({
    mutationFn: async (data: LinkTemplateCreate) => {
      return await LinkTemplatesService.createLinkTemplateApiV1LinkTemplatesPost({
        requestBody: data,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-link-templates"] });
      queryClient.invalidateQueries({ queryKey: ["link-templates"] });
      setSuccess("Link template created successfully");
      closeModal();
      setTimeout(() => setSuccess(null), 3000);
    },
    onError: (err) => {
      setError(extractErrorMessage(err, "Failed to create link template"));
    },
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: number; data: LinkTemplateUpdate }) => {
      return await LinkTemplatesService.updateLinkTemplateApiV1LinkTemplatesTemplateIdPatch({
        templateId: id,
        requestBody: data,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-link-templates"] });
      queryClient.invalidateQueries({ queryKey: ["link-templates"] });
      setSuccess("Link template updated successfully");
      closeModal();
      setTimeout(() => setSuccess(null), 3000);
    },
    onError: (err) => {
      setError(extractErrorMessage(err, "Failed to update link template"));
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      return await LinkTemplatesService.deleteLinkTemplateApiV1LinkTemplatesTemplateIdDelete({
        templateId: id,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-link-templates"] });
      queryClient.invalidateQueries({ queryKey: ["link-templates"] });
      setSuccess("Link template deleted successfully");
      setTimeout(() => setSuccess(null), 3000);
    },
    onError: (err) => {
      setError(extractErrorMessage(err, "Failed to delete link template"));
    },
  });

  // Helper function to extract error message
  const extractErrorMessage = (err: any, fallback: string): string => {
    if (err instanceof ApiError) {
      if (err.body && typeof err.body === "object" && "detail" in err.body) {
        const detail = err.body.detail;
        if (typeof detail === "string") return detail;
        if (typeof detail === "object" && detail !== null && "message" in detail) {
          return (detail as any).message;
        }
      }
      if (err.body && typeof err.body === "object" && "message" in err.body) {
        return (err.body as any).message;
      }
    }
    if (err instanceof Error) {
      return err.message;
    }
    return fallback;
  };

  const openCreateModal = () => {
    setIsEditing(false);
    setEditingId(null);
    setFormData(emptyFormData);
    setFieldNamesInput("");
    setConditionsInput("");
    setShowModal(true);
    setError(null);
  };

  const openEditModal = (template: LinkTemplateRead) => {
    setIsEditing(true);
    setEditingId(template.id);
    setFormData({
      template_id: template.template_id,
      name: template.name,
      icon_name: template.icon_name,
      tooltip_template: template.tooltip_template,
      url_template: template.url_template,
      field_names: template.field_names || [],
      conditions: template.conditions || null,
      enabled: template.enabled ?? true,
      display_order: template.display_order ?? 100,
    });
    setFieldNamesInput((template.field_names || []).join(", "));
    setConditionsInput(template.conditions ? JSON.stringify(template.conditions, null, 2) : "");
    setShowModal(true);
    setError(null);
  };

  const closeModal = () => {
    setShowModal(false);
    setIsEditing(false);
    setEditingId(null);
    setFormData(emptyFormData);
    setFieldNamesInput("");
    setConditionsInput("");
    setIconSearchTerm("");
    setShowIconDropdown(false);
    setError(null);
  };

  const handleSubmit = () => {
    // Parse field_names
    const fieldNames = fieldNamesInput
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    // Parse conditions JSON
    let conditions: Record<string, any> | null = null;
    if (conditionsInput.trim()) {
      try {
        conditions = JSON.parse(conditionsInput);
      } catch (e) {
        setError("Invalid JSON in conditions field");
        return;
      }
    }

    const data = {
      ...formData,
      field_names: fieldNames.length > 0 ? fieldNames : null,
      conditions,
    };

    if (isEditing && editingId !== null) {
      // For update, don't send template_id
      const { template_id, ...updateData } = data;
      updateMutation.mutate({ id: editingId, data: updateData as LinkTemplateUpdate });
    } else {
      createMutation.mutate(data as LinkTemplateCreate);
    }
  };

  const handleDelete = (id: number) => {
    if (window.confirm("Are you sure you want to delete this link template?")) {
      deleteMutation.mutate(id);
    }
  };

  const handleToggleEnabled = async (template: LinkTemplateRead) => {
    updateMutation.mutate({
      id: template.id,
      data: { enabled: !template.enabled },
    });
  };

  if (!isAdmin) {
    return (
      <DefaultPageLayout>
        <div className="container max-w-none flex h-full w-full flex-col items-center justify-center gap-4 bg-default-background">
          <AlertCircle className="text-[48px] text-error text-error-500" />
          <span className="text-heading-2 font-heading-2 text-default-font">
            Access Denied
          </span>
          <span className="text-body font-body text-subtext-color">
            Admin privileges required to manage link templates
          </span>
        </div>
      </DefaultPageLayout>
    );
  }

  const sortedTemplates = templates
    ? [...templates].sort((a, b) => (a.display_order ?? 100) - (b.display_order ?? 100))
    : [];

  return (
    <>
      <AdminPageLayout
        title="Link Templates"
        subtitle="Configure contextual action links for timeline items"
        actionButton={<Button icon={<Plus />} onClick={openCreateModal}>Add Template</Button>}
      >
        {/* Templates Table */}
        {isLoading ? (
          <div className="flex w-full items-center justify-center py-12">
            <span className="text-body font-body text-subtext-color">Loading templates...</span>
          </div>
        ) : sortedTemplates.length === 0 ? (
          <div className="flex w-full items-center justify-center py-12">
            <span className="text-body font-body text-subtext-color">No templates found</span>
          </div>
        ) : (
          <div className="flex w-full flex-col items-start overflow-auto">
              <Table
                header={
                  <Table.HeaderRow>
                    <Table.HeaderCell>Template</Table.HeaderCell>
                    <Table.HeaderCell>Icon</Table.HeaderCell>
                    <Table.HeaderCell>URL Template</Table.HeaderCell>
                    <Table.HeaderCell>Field Names</Table.HeaderCell>
                  <Table.HeaderCell>Order</Table.HeaderCell>
                  <Table.HeaderCell>Enabled</Table.HeaderCell>
                  <Table.HeaderCell />
                </Table.HeaderRow>
              }
            >
              {sortedTemplates.map((template) => {
                const IconComponent = getIconComponent(template.icon_name);
                return (
                  <Table.Row key={template.id}>
                    <Table.Cell>
                      <div className="flex flex-col gap-1">
                        <span className="whitespace-nowrap text-body-bold font-body-bold text-default-font">
                          {template.name}
                        </span>
                        <span className="text-caption font-caption text-neutral-500">
                          {template.template_id}
                        </span>
                      </div>
                    </Table.Cell>
                    <Table.Cell>
                      <div className="text-[20px] text-neutral-700">{IconComponent}</div>
                    </Table.Cell>
                    <Table.Cell>
                      <span className="font-mono text-sm text-neutral-700 max-w-xs truncate">
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
                        {template.display_order}
                      </span>
                    </Table.Cell>
                    <Table.Cell>
                      <Switch
                        checked={template.enabled}
                        onCheckedChange={() => handleToggleEnabled(template)}
                      />
                    </Table.Cell>
                    <Table.Cell>
                      <div className="flex grow shrink-0 basis-0 items-center justify-end">
                        <DropdownMenu.Root>
                          <DropdownMenu.Trigger asChild>
                            <IconButton icon={<MoreHorizontal />} />
                          </DropdownMenu.Trigger>
                          <DropdownMenu.Content
                            side="bottom"
                            align="end"
                            sideOffset={8}
                          >
                            <DropdownMenu.DropdownItem
                              icon={<Edit />}
                              label="Edit"
                              onClick={() => openEditModal(template)}
                            />
                            <DropdownMenu.DropdownDivider />
                            <DropdownMenu.DropdownItem
                              icon={<Trash2 />}
                              label="Delete"
                              onClick={() => handleDelete(template.id)}
                            />
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
      </AdminPageLayout>

      {/* Create/Edit Modal */}
      {showModal && (
        <ModalShell
          title={isEditing ? "Edit Link Template" : "Create Link Template"}
          description="Configure contextual action links for timeline items"
          panelClassName="max-w-2xl max-h-[90vh] overflow-y-auto"
          onClose={closeModal}
        >
              {/* Modal Header */}
              <div className="flex w-full items-center gap-2">
                <div className="flex grow shrink-0 basis-0 flex-col items-start gap-1">
                  <span className="text-heading-2 font-heading-2 text-default-font">
                    {isEditing ? "Edit Link Template" : "Create Link Template"}
                  </span>
                  <span className="text-body font-body text-subtext-color">
                    Configure contextual action links for timeline items
                  </span>
                </div>
                <Link2 className="text-[24px] text-brand-primary" />
              </div>

              {/* Form */}
              <div className="flex w-full items-start rounded-md border border-solid border-neutral-border bg-default-background">
                <div className="flex grow shrink-0 basis-0 flex-col items-start gap-4 px-4 py-4">
                  <TextField
                    className="h-auto w-full flex-none"
                    label="Template ID"
                    helpText="Unique identifier (e.g., 'virustotal-domain')"
                  >
                    <TextField.Input
                      placeholder="template-id"
                      value={formData.template_id}
                      onChange={(e) =>
                        setFormData({ ...formData, template_id: e.target.value })
                      }
                      disabled={isEditing}
                    />
                  </TextField>

                  <TextField
                    className="h-auto w-full flex-none"
                    label="Name"
                    helpText="Human-readable name"
                  >
                    <TextField.Input
                      placeholder="VirusTotal Domain Lookup"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    />
                  </TextField>

                  {/* Icon Selector with Dropdown */}
                  <div className="flex w-full flex-col gap-2">
                    <label className="text-body-bold font-body-bold text-default-font">
                      Icon
                    </label>
                    <span className="text-caption font-caption text-neutral-500">
                      Select an icon for this link template
                    </span>
                    <div className="relative" ref={iconDropdownRef}>
                      <div
                        className="flex w-full items-center gap-2 rounded-md border border-solid border-neutral-border bg-default-background px-3 py-2 cursor-pointer hover:border-neutral-400"
                        onClick={() => setShowIconDropdown(!showIconDropdown)}
                      >
                        <div className="text-[20px] text-neutral-700">
                          {getIconComponent(formData.icon_name)}
                        </div>
                        <span className="flex-1 text-body font-body text-default-font">
                          {formData.icon_name || "Select an icon"}
                        </span>
                        <ChevronDown className="text-[16px] text-neutral-500" />
                      </div>
                      
                      {showIconDropdown && (
                        <div className="absolute z-10 mt-1 w-full rounded-md border border-solid border-neutral-border bg-default-background shadow-lg">
                          <div className="p-2">
                            <TextField className="h-auto w-full">
                              <TextField.Input
                                placeholder="Search icons..."
                                value={iconSearchTerm}
                                onChange={(e) => setIconSearchTerm(e.target.value)}
                                onClick={(e) => e.stopPropagation()}
                              />
                            </TextField>
                          </div>
                          <div className="max-h-64 overflow-y-auto">
                            {filteredIcons.length === 0 ? (
                              <div className="px-4 py-3 text-center text-caption font-caption text-neutral-500">
                                No icons found
                              </div>
                            ) : (
                              filteredIcons.map((iconName) => (
                                <div
                                  key={iconName}
                                  className="flex items-center gap-3 px-4 py-2 cursor-pointer hover:bg-neutral-100"
                                  onClick={() => {
                                    setFormData({ ...formData, icon_name: iconName });
                                    setShowIconDropdown(false);
                                    setIconSearchTerm("");
                                  }}
                                >
                                  <div className="text-[20px] text-neutral-700 flex-shrink-0">
                                    {getIconComponent(iconName)}
                                  </div>
                                  <span className="text-body font-body text-default-font">
                                    {iconName}
                                  </span>
                                </div>
                              ))
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  <TextField
                    className="h-auto w-full flex-none"
                    label="Tooltip Template"
                    helpText="Supports {{variable}} interpolation"
                  >
                    <TextField.Input
                      placeholder="Check {{observable_value}} on VirusTotal"
                      value={formData.tooltip_template}
                      onChange={(e) =>
                        setFormData({ ...formData, tooltip_template: e.target.value })
                      }
                    />
                  </TextField>

                  <TextField
                    className="h-auto w-full flex-none"
                    label="URL Template"
                    helpText="Supports {{variable}} interpolation (values are URL-encoded)"
                  >
                    <TextField.Input
                      placeholder="https://example.com/search?q={{observable_value}}"
                      value={formData.url_template}
                      onChange={(e) =>
                        setFormData({ ...formData, url_template: e.target.value })
                      }
                    />
                  </TextField>

                  <TextField
                    className="h-auto w-full flex-none"
                    label="Field Names"
                    helpText="Comma-separated field names this template applies to"
                  >
                    <TextField.Input
                      placeholder="observable_value, domain, ip_address"
                      value={fieldNamesInput}
                      onChange={(e) => setFieldNamesInput(e.target.value)}
                    />
                  </TextField>

                  <div className="flex w-full flex-col gap-2">
                    <label className="text-body-bold font-body-bold text-default-font">
                      Conditions (JSON)
                    </label>
                    <span className="text-caption font-caption text-neutral-500">
                      Optional: Field/value pairs that must match (e.g., {`{"observable_type": "domain"}`})
                    </span>
                    <textarea
                      className="w-full rounded-md border border-solid border-neutral-border bg-default-background px-3 py-2 font-mono text-sm text-default-font"
                      rows={3}
                      placeholder='{"observable_type": "domain"}'
                      value={conditionsInput}
                      onChange={(e) => setConditionsInput(e.target.value)}
                    />
                  </div>

                  <div className="flex w-full items-center gap-4">
                    <TextField
                      className="h-auto w-32 flex-none"
                      label="Display Order"
                      helpText="Sort order"
                    >
                      <TextField.Input
                        type="number"
                        value={String(formData.display_order)}
                        onChange={(e) =>
                          setFormData({ ...formData, display_order: parseInt(e.target.value) || 0 })
                        }
                      />
                    </TextField>

                    <div className="flex flex-col gap-2">
                      <span className="text-body-bold font-body-bold text-default-font">
                        Enabled
                      </span>
                      <Switch
                        checked={formData.enabled}
                        onCheckedChange={(checked) =>
                          setFormData({ ...formData, enabled: checked })
                        }
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="flex w-full items-center justify-end gap-2">
                <Button variant="neutral-secondary" onClick={closeModal}>
                  Cancel
                </Button>
                <Button
                  onClick={handleSubmit}
                  loading={createMutation.isPending || updateMutation.isPending}
                >
                  {isEditing ? "Save Changes" : "Create Template"}
                </Button>
              </div>
        </ModalShell>
      )}

      {/* Toast Notifications */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
        {error && (
          <Toast
            variant="error"
            icon={<AlertCircle />}
            title="Error"
            description={error}
          />
        )}
        {success && (
          <Toast
            variant="success"
            icon={<CheckCircle />}
            title="Success"
            description={success}
          />
        )}
      </div>
    </>
  );
}

export default AdminLinkTemplates;
