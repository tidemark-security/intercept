import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../../../tests/test-utils";
import { QueueSearchField } from "./QueueSearchField";
import { useState } from "react";

describe("QueueSearchField", () => {
  afterEach(() => vi.useRealTimers());

  it("debounces the final term, holds short input, and clears immediately", () => {
    vi.useFakeTimers();
    const commits = vi.fn();
    function ControlledField() {
      const [query, setQuery] = useState("");
      return <QueueSearchField query={query} onCommit={(next) => { commits(next); setQuery(next); }} />;
    }
    renderWithProviders(<ControlledField />);
    const input = screen.getByRole("textbox", { name: "Search this queue" });
    fireEvent.change(input, { target: { value: "a" } });
    act(() => vi.advanceTimersByTime(300));
    expect(commits).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: "al" } });
    act(() => vi.advanceTimersByTime(150));
    fireEvent.change(input, { target: { value: "alpha   event" } });
    act(() => vi.advanceTimersByTime(299));
    expect(commits).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(commits).toHaveBeenLastCalledWith("alpha event");
    fireEvent.change(input, { target: { value: "a" } });
    expect(commits).toHaveBeenLastCalledWith("");
    expect(input).toHaveValue("a");
    fireEvent.click(screen.getByRole("button", { name: "Clear search" }));
    expect(input).toHaveFocus();
    expect(input).toHaveValue("");
  });

  it("commits on Enter without waiting for the debounce", () => {
    const commits = vi.fn();
    renderWithProviders(<QueueSearchField query="" onCommit={commits} />);
    const input = screen.getByRole("textbox", { name: "Search this queue" });
    fireEvent.change(input, { target: { value: "alpha" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(commits).toHaveBeenCalledWith("alpha");
  });
});
