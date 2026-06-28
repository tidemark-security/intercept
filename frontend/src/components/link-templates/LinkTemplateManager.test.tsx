import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import type { ComponentProps } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../../tests/test-utils";
import { LinkTemplateManager, type ManagedLinkTemplate } from "./LinkTemplateManager";

const template: ManagedLinkTemplate = {
  id: 1,
  template_id: "case-console",
  name: "Case Console",
  icon_name: "Link2",
  tooltip_template: "Open {{human_id}}",
  url_template: "https://console.example/{{human_id}}",
  field_names: ["human_id"],
  conditions: null,
  surface_scopes: ["entity"],
  entity_types: ["case"],
  enabled: true,
  display_order: 10,
};

type ManagerProps = ComponentProps<typeof LinkTemplateManager<ManagedLinkTemplate>>;

beforeEach(() => {
  Object.defineProperty(window.URL, "createObjectURL", {
    configurable: true,
    value: vi.fn(() => "blob:link-template-export"),
  });
  Object.defineProperty(window.URL, "revokeObjectURL", {
    configurable: true,
    value: vi.fn(),
  });
  Object.defineProperty(HTMLAnchorElement.prototype, "click", {
    configurable: true,
    value: vi.fn(),
  });
});

function renderManager(overrides: Partial<ManagerProps> = {}) {
  const props: ManagerProps = {
    title: "Personal Link Templates",
    templates: [template],
    onCreate: vi.fn().mockResolvedValue({}),
    onUpdate: vi.fn().mockResolvedValue({}),
    onDelete: vi.fn().mockResolvedValue({}),
    onImport: vi.fn().mockResolvedValue([template]),
    onExport: vi.fn().mockResolvedValue({ schema_version: 1, templates: [template] }),
    onChanged: vi.fn(),
    ...overrides,
  };

  const result = renderWithProviders(<LinkTemplateManager {...props} />);
  return { ...result, props };
}

describe("LinkTemplateManager", () => {
  it("uses Personal Link Templates copy without the legacy Deep Links label", () => {
    renderManager();

    expect(screen.getByText("Personal Link Templates")).toBeInTheDocument();
    expect(screen.queryByText(/Deep Links/i)).not.toBeInTheDocument();
  });

  it("creates templates with scope and entity type fields", async () => {
    const onCreate = vi.fn().mockResolvedValue({});
    renderManager({ templates: [], onCreate });

    fireEvent.click(screen.getByRole("button", { name: /Add Template/i }));
    fireEvent.change(screen.getByLabelText("Template ID"), { target: { value: "case-parent" } });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Case Parent" } });
    fireEvent.change(screen.getByLabelText("Tooltip Template"), { target: { value: "Open {{human_id}}" } });
    fireEvent.change(screen.getByLabelText("URL Template"), { target: { value: "https://example/{{human_id}}" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Parent entity" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Cases" }));
    fireEvent.click(screen.getByRole("button", { name: /Create Template/ }));

    await waitFor(() => expect(onCreate).toHaveBeenCalled());
    expect(onCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        template_id: "case-parent",
        surface_scopes: ["timeline_item", "entity"],
        entity_types: ["case"],
      }),
    );
  });

  it("imports a JSON bundle from the file input", async () => {
    const onImport = vi.fn().mockResolvedValue([template]);
    const { container } = renderManager({ onImport });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(
      [JSON.stringify({ schema_version: 1, templates: [template] })],
      "template.json",
      { type: "application/json" },
    );

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(onImport).toHaveBeenCalled());
    expect(onImport).toHaveBeenCalledWith(
      expect.objectContaining({
        schema_version: 1,
        templates: expect.any(Array),
      }),
    );
  });

  it("exports a selected template as a portable JSON bundle", async () => {
    const onExport = vi.fn().mockResolvedValue({ schema_version: 1, templates: [template] });
    renderManager({ onExport });

    const row = screen.getByText("case-console").closest("tr");
    expect(row).not.toBeNull();

    fireEvent.pointerDown(within(row as HTMLElement).getByRole("button", { name: "Actions for Case Console" }));
    fireEvent.click(await screen.findByText("Export"));

    await waitFor(() => expect(onExport).toHaveBeenCalledWith([template.id]));
    expect(window.URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalled();
  });
});
