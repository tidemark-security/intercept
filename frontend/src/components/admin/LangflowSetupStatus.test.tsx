import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LangflowSetupStatus } from "./LangflowSetupStatus";


describe("LangflowSetupStatus", () => {
  it("renders compact warnings once while keeping non-warning step statuses", () => {
    render(
      <LangflowSetupStatus
        status={{
          success: true,
          message: "Intercept MCP server setup completed with warnings",
          steps: [
            {
              id: "nhi_account",
              label: "Automation NHI account",
              status: "created",
              message: "Created NHI account 'tidemark_ai'",
            },
            {
              id: "flow:tmi_general_purpose",
              label: "General purpose flow",
              status: "warning",
              message:
                "Existing flow 'General purpose flow' differs from the bundled asset and was not overwritten",
            },
          ],
          warnings: [
            "Existing flow 'General purpose flow' differs from the bundled asset and was not overwritten",
          ],
          api_key: {
            id: "api-key-id",
            user_id: "user-id",
            name: "Intercept Langflow MCP",
            prefix: "tmk_1234",
            expires_at: "2026-01-01T00:00:00Z",
            last_used_at: null,
            revoked_at: null,
            created_at: "2025-01-01T00:00:00Z",
          },
        }}
        isDarkTheme={false}
      />, 
    );

    expect(
      screen.getByText("Langflow setup completed with warnings"),
    ).toBeInTheDocument();
    expect(screen.getByText("Automation NHI account")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Existing flow 'General purpose flow' differs from the bundled asset and was not overwritten",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("General purpose flow")).not.toBeInTheDocument();
    expect(screen.queryByText("Copy the generated API key now")).not.toBeInTheDocument();
  });
});
