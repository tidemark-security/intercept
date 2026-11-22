import { StrictMode } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import Login from "@/pages/Login";
import { ApiError } from "@/types/generated/core/ApiError";
import type { LoginResponse } from "@/types/generated/models/LoginResponse";
import { AuthenticationService } from "@/types/generated/services/AuthenticationService";
import { SessionProvider } from "./SessionProvider";
import { ThemeProvider } from "./ThemeContext";

const sessionPath = "/api/v1/auth/session";
const activeSession: LoginResponse = {
  user: { id: "user-1", username: "analyst", role: "ANALYST", status: "ACTIVE" },
  session: { sessionId: "session-1", expiresAt: "2026-12-01T00:00:00Z" },
};

function apiError(status: number) {
  return new ApiError(
    { method: "GET", url: sessionPath },
    { ok: false, status, statusText: "", url: sessionPath, body: {} },
    "Session check failed",
  );
}

function openTab(path = "/cases/CAS-0000001") {
  return render(
    <StrictMode>
      <ThemeProvider>
        <MemoryRouter initialEntries={[path]}>
          <SessionProvider>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route
                path="/cases/:caseId"
                element={<ProtectedRoute><h1>Case details</h1></ProtectedRoute>}
              />
            </Routes>
          </SessionProvider>
        </MemoryRouter>
      </ThemeProvider>
    </StrictMode>,
  );
}

describe("restoring a session in a new tab", () => {
  const getSession = vi.spyOn(AuthenticationService, "getSessionApiV1AuthSessionGet");
  const getOidcConfig = vi.spyOn(AuthenticationService, "getOidcConfigApiV1AuthOidcConfigGet");

  beforeEach(() => {
    vi.useFakeTimers();
    getSession.mockReset().mockResolvedValue(activeSession);
    getOidcConfig.mockReset().mockResolvedValue({ enabled: true, providerName: "SSO" });
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("keeps the requested page while a busy session check retries", async () => {
    getSession.mockRejectedValueOnce(apiError(503));

    await act(async () => { openTab(); });

    expect(screen.queryByRole("button", { name: "Sign in with SSO" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Case details" })).not.toBeInTheDocument();
    expect(getSession).toHaveBeenCalledTimes(1);

    await act(() => vi.advanceTimersByTimeAsync(1000));

    expect(getSession).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("heading", { name: "Case details" })).toBeInTheDocument();
  });

  it("makes a single startup check under StrictMode", async () => {
    await act(async () => { openTab(); });

    expect(screen.getByRole("heading", { name: "Case details" })).toBeInTheDocument();
    expect(getSession).toHaveBeenCalledTimes(1);
  });

  it("asks for SSO when the server confirms there is no active session", async () => {
    getSession.mockRejectedValue(apiError(401));

    await act(async () => { openTab(); });

    expect(screen.getByRole("button", { name: "Sign in with SSO" })).toBeInTheDocument();
    expect(getSession).toHaveBeenCalledTimes(1);
  });

  it("offers a session recheck from the login URL when automatic retries run out", async () => {
    getSession.mockRejectedValue(apiError(503));

    await act(async () => { openTab("/login"); });

    expect(screen.queryByRole("button", { name: "Sign in with SSO" })).not.toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(3000));

    const retry = screen.getByRole("button", { name: /Retry session check/ });
    expect(getSession).toHaveBeenCalledTimes(3);
    expect(screen.queryByRole("button", { name: "Sign in with SSO" })).not.toBeInTheDocument();

    getSession.mockRejectedValue(apiError(401));
    await act(async () => { fireEvent.click(retry); });

    expect(screen.getByRole("button", { name: "Sign in with SSO" })).toBeInTheDocument();
  });
});
