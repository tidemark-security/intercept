import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider } from "@/contexts/ThemeContext";
import McpConsent from "./McpConsent";

const consentContext = {
  transaction_id: "transaction-123",
  csrf_token: "csrf-456",
  client_name: "Claude Desktop",
  client_id: "client-789",
  client_uri: "https://claude.ai",
  redirect_uri: "http://127.0.0.1:6274/oauth/callback",
  scopes: ["openid", "offline_access"],
  verified_domain: "claude.ai",
};

describe("McpConsent", () => {
  afterEach(() => {
    document.cookie = "XSRF-TOKEN=; Max-Age=0; Path=/";
    vi.unstubAllGlobals();
  });

  it("renders the native consent fields without sending ambient app credentials", async () => {
    document.cookie = "XSRF-TOKEN=app-csrf-token; Path=/";
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue(consentContext),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { container } = render(
      <MemoryRouter initialEntries={["/oauth/mcp/consent#txn_id=transaction-123"]}>
        <ThemeProvider>
          <McpConsent />
        </ThemeProvider>
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", { name: "Authorize MCP access" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Claude Desktop wants to connect")).toBeInTheDocument();
    expect(screen.getByText("Verified domain: claude.ai")).toBeInTheDocument();
    expect(screen.getAllByText(consentContext.redirect_uri)).toHaveLength(2);
    expect(screen.getByAltText("Tidemark Intercept")).toBeInTheDocument();
    expect(screen.getAllByAltText("Tidemark Security")).toHaveLength(2);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/mcp/oauth/consent/oidc",
        {
          method: "POST",
          credentials: "omit",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ transaction_id: "transaction-123" }),
        },
      );
    });

    const form = container.querySelector("form");
    expect(form).toHaveAttribute("action", "/mcp/consent");
    expect(form).toHaveAttribute("method", "post");
    expect(form?.querySelector('input[name="txn_id"]')).toHaveValue(
      consentContext.transaction_id,
    );
    expect(form?.querySelector('input[name="csrf_token"]')).toHaveValue(
      consentContext.csrf_token,
    );
    expect(form?.querySelector('input[name="submit"]')).toHaveValue("true");
    const denyButton = form?.querySelector('button[value="deny"]');
    const approveButton = form?.querySelector('button[value="approve"]');
    expect(denyButton).toHaveAttribute("name", "action");
    expect(denyButton).toHaveTextContent("Deny");
    expect(approveButton).toHaveAttribute("name", "action");
    expect(approveButton).toHaveTextContent("Authorize");
  });
});
