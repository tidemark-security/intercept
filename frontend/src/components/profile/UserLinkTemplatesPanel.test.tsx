import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../../tests/test-utils";
import { UserLinkTemplatesPanel } from "./UserLinkTemplatesPanel";

const personalLinkTemplateServiceMock = vi.hoisted(() => ({
  get: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  delete: vi.fn(),
  import: vi.fn(),
  export: vi.fn(),
}));

vi.mock("@/types/generated/services/PersonalLinkTemplatesService", () => ({
  PersonalLinkTemplatesService: {
    getPersonalLinkTemplatesApiV1PersonalLinkTemplatesGet: personalLinkTemplateServiceMock.get,
    createPersonalLinkTemplateApiV1PersonalLinkTemplatesPost: personalLinkTemplateServiceMock.create,
    updatePersonalLinkTemplateApiV1PersonalLinkTemplatesTemplateIdPatch: personalLinkTemplateServiceMock.update,
    deletePersonalLinkTemplateApiV1PersonalLinkTemplatesTemplateIdDelete: personalLinkTemplateServiceMock.delete,
    importPersonalLinkTemplatesApiV1PersonalLinkTemplatesImportPost: personalLinkTemplateServiceMock.import,
    exportPersonalLinkTemplatesApiV1PersonalLinkTemplatesExportPost: personalLinkTemplateServiceMock.export,
  },
}));

const template = {
  id: 2,
  user_id: "00000000-0000-4000-8000-000000000001",
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
  created_at: "2026-06-28T00:00:00Z",
  updated_at: "2026-06-28T00:00:00Z",
};

const copiedTemplate = {
  ...template,
  id: 3,
  template_id: "case-console-copy",
  name: "Case Console (copy)",
};

beforeEach(() => {
  personalLinkTemplateServiceMock.get
    .mockResolvedValueOnce([template])
    .mockResolvedValue([template, copiedTemplate]);
  personalLinkTemplateServiceMock.import.mockResolvedValue([copiedTemplate]);
  personalLinkTemplateServiceMock.export.mockResolvedValue({ schema_version: 1, templates: [template] });
  Object.defineProperty(window.URL, "createObjectURL", {
    configurable: true,
    value: vi.fn(() => "blob:personal-link-template-export"),
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

describe("UserLinkTemplatesPanel", () => {
  it("can render personal link template actions inline with the settings subheader", async () => {
    renderWithProviders(
      <UserLinkTemplatesPanel
        headerIcon={<span data-testid="personal-link-template-icon" />}
        headerVariant="settings-card"
      />,
    );

    const heading = await screen.findByRole("heading", {
      name: "Personal Link Templates",
    });
    const headerRow = heading.closest("div")?.parentElement;

    expect(headerRow).toHaveClass("border-b");
    expect(within(headerRow as HTMLElement).getByRole("button", { name: /Import/i })).toBeInTheDocument();
    expect(
      within(headerRow as HTMLElement).getByRole("button", {
        name: /Add Personal Template/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("personal-link-template-icon")).toBeInTheDocument();
  });

  it("uses Personal Link Templates copy and personal import/export services", async () => {
    const { container } = renderWithProviders(<UserLinkTemplatesPanel />);

    expect(await screen.findByText("Personal Link Templates")).toBeInTheDocument();
    expect(screen.queryByText(/Deep Links/i)).not.toBeInTheDocument();
    expect(await screen.findByText("case-console")).toBeInTheDocument();

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File([JSON.stringify({ schema_version: 1, templates: [template] })], "personal.json", {
      type: "application/json",
    });
    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => expect(personalLinkTemplateServiceMock.import).toHaveBeenCalledWith({
      requestBody: expect.objectContaining({
        schema_version: 1,
        templates: expect.any(Array),
      }),
    }));
    expect(await screen.findByText("case-console-copy")).toBeInTheDocument();

    const row = screen.getByText("case-console").closest("tr");
    expect(row).not.toBeNull();
    fireEvent.pointerDown(within(row as HTMLElement).getByRole("button", { name: "Actions for Case Console" }));
    fireEvent.click(await screen.findByText("Export"));

    await waitFor(() => expect(personalLinkTemplateServiceMock.export).toHaveBeenCalledWith({
      requestBody: { template_ids: [template.id] },
    }));
  });
});
