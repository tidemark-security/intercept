import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../../tests/test-utils";
import { MenuCard } from "@/components/cards/MenuCard";

describe("MenuCard", () => {
  it("renders tags as search links", () => {
    const { container } = renderWithProviders(
      <MenuCard id="ALT-0000001" title="Suspicious login" tags={["phishing"]} />
    );

    const tagLink = screen.getByRole("link", { name: "phishing" });

    expect(tagLink).toHaveAttribute("href", "/search?tag=phishing");
    expect(container.querySelector(".lucide-plus")).not.toBeInTheDocument();
    expect(container.querySelector(".lucide-minus")).not.toBeInTheDocument();
  });

  it("uses a regular tag click to include-filter the tag when a filter handler is provided", async () => {
    const user = userEvent.setup();
    const onTagClick = vi.fn();

    renderWithProviders(
      <MenuCard id="ALT-0000001" title="Suspicious login" tags={["phishing"]} onTagClick={onTagClick} />
    );

    await user.click(screen.getByRole("link", { name: "phishing" }));

    expect(onTagClick).toHaveBeenCalledWith("phishing", "include");
    expect(screen.getByRole("button", { name: "Include phishing" })).toBeInTheDocument();
  });

  it("uses ctrl/cmd tag clicks to exclude-filter the tag", () => {
    const onTagClick = vi.fn();

    renderWithProviders(
      <MenuCard id="ALT-0000001" title="Suspicious login" tags={["phishing"]} onTagClick={onTagClick} />
    );

    fireEvent.click(screen.getByRole("link", { name: "phishing" }), { ctrlKey: true });

    expect(onTagClick).toHaveBeenCalledWith("phishing", "exclude");
  });

  it("keeps middle-click search links from triggering filter clicks", () => {
    const onTagClick = vi.fn();

    renderWithProviders(
      <MenuCard id="ALT-0000001" title="Suspicious login" tags={["phishing"]} onTagClick={onTagClick} />
    );

    const tagLink = screen.getByRole("link", { name: "phishing" });

    fireEvent(tagLink, new MouseEvent("auxclick", { bubbles: true, button: 1 }));

    expect(tagLink).toHaveAttribute("href", "/search?tag=phishing");
    expect(onTagClick).not.toHaveBeenCalled();
  });

});
