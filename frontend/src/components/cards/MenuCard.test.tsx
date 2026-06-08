import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../../tests/test-utils";
import { MenuCard } from "@/components/cards/MenuCard";

describe("MenuCard", () => {
  it("routes tag clicks to include and modified clicks to exclude", () => {
    const onTagClick = vi.fn();

    const { container } = renderWithProviders(
      <MenuCard id="ALT-0000001" title="Suspicious login" tags={["phishing"]} onTagClick={onTagClick} />
    );

    const tagButton = screen.getByRole("button", { name: /add phishing to include tag filter/i });

    expect(container.querySelector(".lucide-plus")).toBeInTheDocument();
    expect(container.querySelector(".lucide-minus")).not.toBeInTheDocument();

    fireEvent.keyDown(window, { key: "Control" });
    expect(screen.getByRole("button", { name: /add phishing to exclude tag filter/i })).toBeInTheDocument();
    expect(container.querySelector(".lucide-minus")).toBeInTheDocument();
    expect(container.querySelector(".lucide-plus")).not.toBeInTheDocument();

    fireEvent.keyUp(window, { key: "Control" });
    expect(screen.getByRole("button", { name: /add phishing to include tag filter/i })).toBeInTheDocument();
    expect(container.querySelector(".lucide-plus")).toBeInTheDocument();
    expect(container.querySelector(".lucide-minus")).not.toBeInTheDocument();

    fireEvent.click(tagButton);
    fireEvent.click(tagButton, { ctrlKey: true });
    fireEvent.click(tagButton, { metaKey: true });

    expect(onTagClick).toHaveBeenNthCalledWith(1, "phishing", "include");
    expect(onTagClick).toHaveBeenNthCalledWith(2, "phishing", "exclude");
    expect(onTagClick).toHaveBeenNthCalledWith(3, "phishing", "exclude");
  });

  it("keeps priority colors partially visible", () => {
    const { container } = renderWithProviders(
      <MenuCard id="ALT-0000001" title="Suspicious login" priority="high" />
    );

    expect(container.innerHTML).toContain("grayscale-[50%]");
    expect(container.innerHTML).not.toContain("saturate-0");
  });
});
