import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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

  it("keeps priority colors partially visible", () => {
    const { container } = renderWithProviders(
      <MenuCard id="ALT-0000001" title="Suspicious login" priority="high" />
    );

    expect(container.innerHTML).toContain("grayscale-[50%]");
    expect(container.innerHTML).not.toContain("saturate-0");
  });
});
