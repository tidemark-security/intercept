import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../tests/test-utils";
import type { SessionContextValue } from "@/contexts/sessionContext";
import AdminLinkTemplates from "./AdminLinkTemplates";

const linkTemplateServiceMock = vi.hoisted(() => ({
  get: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  delete: vi.fn(),
  import: vi.fn(),
  export: vi.fn(),
}));

vi.mock("@/types/generated/services/LinkTemplatesService", () => ({
  LinkTemplatesService: {
    getLinkTemplatesApiV1LinkTemplatesGet: linkTemplateServiceMock.get,
    createLinkTemplateApiV1LinkTemplatesPost: linkTemplateServiceMock.create,
    updateLinkTemplateApiV1LinkTemplatesTemplateIdPatch: linkTemplateServiceMock.update,
    deleteLinkTemplateApiV1LinkTemplatesTemplateIdDelete: linkTemplateServiceMock.delete,
    importLinkTemplatesApiV1LinkTemplatesImportPost: linkTemplateServiceMock.import,
    exportLinkTemplatesApiV1LinkTemplatesExportPost: linkTemplateServiceMock.export,
  },
}));

const template = {
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
  created_at: "2026-06-28T00:00:00Z",
  updated_at: "2026-06-28T00:00:00Z",
};

function adminSession(): SessionContextValue {
  return {
    status: "authenticated",
    user: { username: "admin", role: "ADMIN" } as SessionContextValue["user"],
    session: null,
    mustChangePassword: false,
    localCredentialManagementAllowed: true,
    lockout: null,
    error: null,
    login: vi.fn(),
    loginWithPasskey: vi.fn(),
    logout: vi.fn(),
    refreshSession: vi.fn(),
    resolveError: vi.fn(),
    acknowledgeLockout: vi.fn(),
    setMustChangePassword: vi.fn(),
    isAdmin: true,
    isAnalyst: false,
    isAuditor: false,
  };
}

beforeEach(() => {
  linkTemplateServiceMock.get.mockResolvedValue([template]);
  linkTemplateServiceMock.import.mockResolvedValue([template]);
  linkTemplateServiceMock.export.mockResolvedValue({ schema_version: 1, templates: [template] });
  Object.defineProperty(window.URL, "createObjectURL", {
    configurable: true,
    value: vi.fn(() => "blob:public-link-template-export"),
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

describe("AdminLinkTemplates", () => {
  it("imports and exports public link template JSON through the generated public service", async () => {
    const { container } = renderWithProviders(<AdminLinkTemplates />, { sessionValue: adminSession() });

    await screen.findByText("case-console");

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File([JSON.stringify({ schema_version: 1, templates: [template] })], "public.json", {
      type: "application/json",
    });
    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => expect(linkTemplateServiceMock.import).toHaveBeenCalledWith({
      requestBody: expect.objectContaining({
        schema_version: 1,
        templates: expect.any(Array),
      }),
    }));

    const row = screen.getByText("case-console").closest("tr");
    expect(row).not.toBeNull();
    fireEvent.pointerDown(within(row as HTMLElement).getByRole("button", { name: "Actions for Case Console" }));
    fireEvent.click(await screen.findByText("Export"));

    await waitFor(() => expect(linkTemplateServiceMock.export).toHaveBeenCalledWith({
      requestBody: { template_ids: [template.id] },
    }));
  });
});
