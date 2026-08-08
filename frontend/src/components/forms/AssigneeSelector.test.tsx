import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../../tests/test-utils";
import { AssigneeSelector } from "./AssigneeSelector";

const users = [
  { userId: "u-1", username: "alice", email: "alice@example.com" },
  { userId: "u-2", username: "bob", email: "bob@example.com" },
];

describe("AssigneeSelector (filter mode)", () => {
  it("selects the current user when 'Assigned to me' is chosen", async () => {
    const user = userEvent.setup();
    const onSelectionChange = vi.fn();

    renderWithProviders(
      <AssigneeSelector
        presentation="toolbar"
        mode="filter"
        currentUser="alice"
        users={users}
        onSelectionChange={onSelectionChange}
      />,
    );

    await user.click(screen.getByRole("button", { name: /assignee/i }));
    await user.click(screen.getByRole("menuitem", { name: /assigned to me/i }));

    expect(onSelectionChange).toHaveBeenCalledWith(["alice"]);
  });

  it("shows 'Assigned to me' when the current user is in a multi-select", async () => {
    const user = userEvent.setup();

    renderWithProviders(
      <AssigneeSelector
        presentation="toolbar"
        mode="filter"
        currentUser="alice"
        selectedAssignees={["alice", "bob"]}
        users={users}
        onSelectionChange={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /2 assignees/i }));

    expect(screen.getByRole("menuitem", { name: /assigned to me/i })).toBeInTheDocument();
  });

  it("keeps the current user selected when another user is added", async () => {
    const user = userEvent.setup();
    const onSelectionChange = vi.fn();

    renderWithProviders(
      <AssigneeSelector
        presentation="toolbar"
        mode="filter"
        currentUser="alice"
        selectedAssignees={["alice"]}
        users={users}
        onSelectionChange={onSelectionChange}
      />,
    );

    await user.click(screen.getByRole("button", { name: /assignee alice/i }));
    await user.click(screen.getByRole("menuitem", { name: /^bob/i }));

    expect(onSelectionChange).toHaveBeenCalledWith(["alice", "bob"]);
  });
});
