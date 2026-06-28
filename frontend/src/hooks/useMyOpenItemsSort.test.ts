import { describe, expect, it } from "vitest";

import {
  formatOpenItemAge,
  getNextMyOpenItemsSort,
  type MyOpenItem,
  sortMyOpenItems,
} from "./useMyOpenItemsSort";

function item(overrides: Partial<MyOpenItem>): MyOpenItem {
  return {
    id: 1,
    human_id: "INT-1",
    title: "Item",
    item_type: "alert",
    priority: "INFO",
    status: "NEW",
    updated_at: "2026-05-24T00:00:00Z",
    ...overrides,
  };
}

describe("useMyOpenItemsSort helpers", () => {
  it("formats age from created_at", () => {
    const now = new Date("2026-05-24T12:00:00Z");

    expect(formatOpenItemAge("2026-05-24T11:59:45Z", now)).toBe("<1m");
    expect(formatOpenItemAge("2026-05-24T11:45:00Z", now)).toBe("15m");
    expect(formatOpenItemAge("2026-05-24T07:00:00Z", now)).toBe("5h");
    expect(formatOpenItemAge("2026-05-21T12:00:00Z", now)).toBe("3d");
    expect(formatOpenItemAge(null, now)).toBe("Unknown");
  });

  it("sorts age ascending by oldest created_at first", () => {
    const items = [
      item({ id: 1, human_id: "TASK-3", created_at: "2026-05-23T12:00:00Z" }),
      item({ id: 2, human_id: "ALERT-1", created_at: "2026-05-20T12:00:00Z" }),
      item({ id: 3, human_id: "CASE-2", created_at: "2026-05-22T12:00:00Z" }),
    ];

    expect(sortMyOpenItems(items, { key: "age", direction: "asc" }).map((openItem) => openItem.human_id)).toEqual([
      "ALERT-1",
      "CASE-2",
      "TASK-3",
    ]);
  });

  it("sorts meaningful visible columns", () => {
    const items = [
      item({ human_id: "TASK-10", title: "Zulu", item_type: "task", status: "TODO", priority: "LOW" }),
      item({ human_id: "ALERT-2", title: "Alpha", item_type: "alert", status: "ESCALATED", priority: "CRITICAL" }),
      item({ human_id: "CASE-1", title: "Bravo", item_type: "case", status: "IN_PROGRESS", priority: "MEDIUM" }),
    ];

    expect(sortMyOpenItems(items, { key: "human_id", direction: "asc" }).map((openItem) => openItem.human_id)).toEqual([
      "ALERT-2",
      "CASE-1",
      "TASK-10",
    ]);
    expect(sortMyOpenItems(items, { key: "title", direction: "asc" }).map((openItem) => openItem.title)).toEqual([
      "Alpha",
      "Bravo",
      "Zulu",
    ]);
    expect(sortMyOpenItems(items, { key: "item_type", direction: "asc" }).map((openItem) => openItem.item_type)).toEqual([
      "alert",
      "case",
      "task",
    ]);
    expect(sortMyOpenItems(items, { key: "status", direction: "asc" }).map((openItem) => openItem.status)).toEqual([
      "ESCALATED",
      "IN_PROGRESS",
      "TODO",
    ]);
    expect(sortMyOpenItems(items, { key: "priority", direction: "desc" }).map((openItem) => openItem.priority)).toEqual([
      "CRITICAL",
      "MEDIUM",
      "LOW",
    ]);
  });

  it("uses oldest-first as the default direction when switching to age sort", () => {
    expect(getNextMyOpenItemsSort({ key: "priority", direction: "desc" }, "age")).toEqual({
      key: "age",
      direction: "asc",
    });
  });
});
