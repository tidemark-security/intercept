import { describe, expect, it } from "vitest";

import { filterSlashCommands, parseSlashCommand } from "./slashCommands";

describe("slashCommands", () => {
  it("parses /run as the case runbook command", () => {
    expect(parseSlashCommand("/run")?.type).toBe("case_runbook");
    expect(parseSlashCommand("/run")?.label).toBe("/run");
  });

  it("does not keep the old /tpl command alias", () => {
    expect(parseSlashCommand("/tpl")).toBeNull();
  });

  it("filters the runbook command by its new command text", () => {
    expect(filterSlashCommands("/ru")).toEqual([
      expect.objectContaining({
        command: "run",
        type: "case_runbook",
        description: "Apply a Case Runbook",
      }),
    ]);
  });
});
