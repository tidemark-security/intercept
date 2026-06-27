import React from "react";
import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CaseClosureModal } from "./CaseClosureModal";
import { renderWithProviders } from "../../../tests/test-utils";

import type { AlertStatus } from "@/types/generated/models/AlertStatus";

vi.mock("@/hooks/useFeatureFlags", () => ({
  useFeatureFlags: () => ({ data: { case_closure_recommended_tags: [] } }),
}));

vi.mock("@/components/forms/Select", () => {
  const Select = ({
    children,
    disabled,
    onValueChange,
    placeholder,
    value,
  }: {
    children: React.ReactNode;
    disabled?: boolean;
    onValueChange: (value: string) => void;
    placeholder?: string;
    value?: string;
  }) => (
    <select
      aria-label={placeholder || "Select"}
      disabled={disabled}
      value={value ?? ""}
      onChange={(event) => onValueChange(event.target.value)}
    >
      <option value="">{placeholder}</option>
      {children}
    </select>
  );

  Select.Item = ({ value }: { children: React.ReactNode; value: string }) => (
    <option value={value}>{value}</option>
  );

  return { Select };
});

const linkedAlert = (id: number, status: AlertStatus) => ({
  id,
  human_id: `ALT-${String(id).padStart(7, "0")}`,
  title: `Alert ${id}`,
  status,
});

function renderModal(
  linkedAlerts = [
    linkedAlert(1, "ESCALATED"),
    linkedAlert(2, "CLOSED_TP"),
  ],
  onConfirm = vi.fn(),
) {
  renderWithProviders(
    <CaseClosureModal
      open
      onOpenChange={vi.fn()}
      linkedAlerts={linkedAlerts}
      linkedTaskCount={0}
      initialTags={[]}
      onConfirm={onConfirm}
    />,
  );

  return onConfirm;
}

describe("CaseClosureModal", () => {
  it("selects open linked alerts by default and renders closed alerts read-only", () => {
    renderModal();

    expect(screen.getByLabelText("Select all open linked alerts")).toBeChecked();
    expect(screen.getByLabelText("Select ALT-0000001")).toBeChecked();
    expect(screen.getByLabelText("Select ALT-0000002")).toBeDisabled();
    expect(screen.getByText("Closed (True Positive)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /close case/i })).toBeDisabled();
  });

  it("select-all toggles only open linked alerts", () => {
    renderModal([
      linkedAlert(1, "ESCALATED"),
      linkedAlert(2, "IN_PROGRESS"),
      linkedAlert(3, "CLOSED_FP"),
    ]);

    fireEvent.click(screen.getByLabelText("Select all open linked alerts"));

    expect(screen.getByLabelText("Select ALT-0000001")).not.toBeChecked();
    expect(screen.getByLabelText("Select ALT-0000002")).not.toBeChecked();
    expect(screen.getByLabelText("Select ALT-0000003")).toBeDisabled();
    expect(screen.getByText("0 of 2 open alerts selected")).toBeInTheDocument();
  });

  it("uses selection only for bulk resolution and submits every open alert", () => {
    const onConfirm = renderModal([
      linkedAlert(1, "ESCALATED"),
      linkedAlert(2, "IN_PROGRESS"),
    ]);

    const resolutionSelects = screen.getAllByLabelText("Resolution");
    const bulkResolutionSelect = resolutionSelects[0];
    const firstRowResolutionSelect = resolutionSelects[1];
    const secondRowResolutionSelect = resolutionSelects[2];

    fireEvent.change(bulkResolutionSelect, { target: { value: "CLOSED_FP" } });
    expect(firstRowResolutionSelect).toHaveValue("CLOSED_FP");
    expect(secondRowResolutionSelect).toHaveValue("CLOSED_FP");

    fireEvent.click(screen.getByLabelText("Select ALT-0000002"));
    fireEvent.change(bulkResolutionSelect, { target: { value: "CLOSED_TP" } });
    expect(firstRowResolutionSelect).toHaveValue("CLOSED_TP");
    expect(secondRowResolutionSelect).toHaveValue("CLOSED_FP");
    expect(secondRowResolutionSelect).not.toBeDisabled();

    fireEvent.change(firstRowResolutionSelect, { target: { value: "CLOSED_BP" } });
    fireEvent.click(screen.getByRole("button", { name: /close case/i }));

    expect(onConfirm).toHaveBeenCalledWith({
      alert_updates: [
        { alert_id: 1, status: "CLOSED_BP" },
        { alert_id: 2, status: "CLOSED_FP" },
      ],
      tags: [],
      note: undefined,
    });
  });

  it("requires every open alert to have a resolution even when not selected for bulk edits", () => {
    const onConfirm = renderModal([
      linkedAlert(1, "ESCALATED"),
      linkedAlert(2, "IN_PROGRESS"),
    ]);

    const resolutionSelects = screen.getAllByLabelText("Resolution");
    const firstRowResolutionSelect = resolutionSelects[1];

    fireEvent.click(screen.getByLabelText("Select ALT-0000002"));
    fireEvent.change(firstRowResolutionSelect, { target: { value: "CLOSED_TP" } });

    expect(screen.getByRole("button", { name: /close case/i })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /close case/i }));
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("allows case closure without alert updates when there are no open linked alerts", () => {
    const onConfirm = renderModal([
      linkedAlert(1, "CLOSED_TP"),
      linkedAlert(2, "CLOSED_FP"),
    ]);

    expect(screen.queryByLabelText("Select all open linked alerts")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /close case/i }));

    expect(onConfirm).toHaveBeenCalledWith({
      alert_updates: [],
      tags: [],
      note: undefined,
    });
  });
});
