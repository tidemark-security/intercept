import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LangflowConnectionStatus } from "./LangflowConnectionStatus";


describe("LangflowConnectionStatus", () => {
  it("renders a mixed pass/fail LangFlow validation report", () => {
    render(
      <LangflowConnectionStatus
        status={{
          success: false,
          message: "2 of 3 LangFlow checks passed",
          checks: [
            {
              id: "connectivity",
              label: "Connectivity",
              success: true,
              message: "Connected to the LangFlow health endpoint",
            },
            {
              id: "flow_listing",
              label: "Authenticated flow listing",
              success: true,
              message: "Authenticated LangFlow API returned 4 flows",
            },
            {
              id: "configured_flows",
              label: "Configured flow existence",
              success: false,
              message: "Missing configured LangFlow flows: Task detail flow (tmi_task_agent)",
            },
          ],
        }}
        isDarkTheme={false}
      />, 
    );

    expect(
      screen.getByText("LangFlow environment checks partially passed"),
    ).toBeInTheDocument();
    expect(screen.getByText("2 of 3 LangFlow checks passed")).toBeInTheDocument();
    expect(screen.getByText("Connectivity")).toBeInTheDocument();
    expect(screen.getByText("Authenticated flow listing")).toBeInTheDocument();
    expect(screen.getByText("Configured flow existence")).toBeInTheDocument();
    expect(
      screen.getByText("Missing configured LangFlow flows: Task detail flow (tmi_task_agent)"),
    ).toBeInTheDocument();
  });

  it("renders a fully successful LangFlow validation report", () => {
    render(
      <LangflowConnectionStatus
        status={{
          success: true,
          message: "LangFlow connectivity, flow listing, and configured flow checks passed",
          checks: [
            {
              id: "connectivity",
              label: "Connectivity",
              success: true,
              message: "Connected to the LangFlow health endpoint",
            },
            {
              id: "flow_listing",
              label: "Authenticated flow listing",
              success: true,
              message: "Authenticated LangFlow API returned 4 flows",
            },
            {
              id: "configured_flows",
              label: "Configured flow existence",
              success: true,
              message: "Validated 4 configured LangFlow flow references",
            },
          ],
        }}
        isDarkTheme={true}
      />,
    );

    expect(
      screen.getByText("LangFlow environment checks passed"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("LangFlow connectivity, flow listing, and configured flow checks passed"),
    ).toBeInTheDocument();
  });
});