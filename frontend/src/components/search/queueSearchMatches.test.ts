import { describe, expect, it } from "vitest";
import { buildQueueSearchPattern, splitQueueSearchText } from "./queueSearchMatches";

const matches = (query: string, text: string) =>
  splitQueueSearchText(text, buildQueueSearchPattern(query))?.filter((part) => part.match).map((part) => part.text);

describe("queue search highlights", () => {
  it("matches quoted phrases and positive terms literally and case-insensitively", () => {
    expect(matches('"login denied" OR admin -ignore -"skip me"', "Login Denied by Admin, ignore or skip me"))
      .toEqual(["Login Denied", "Admin"]);
    expect(matches("user.name +team", "userXname user.name +team")).toEqual(["user.name", "+team"]);
  });

  it("highlights the canonical entity ID for an exact shortened ID", () => {
    expect(matches("cas-12", "CAS-0000012 CAS-0000123")).toEqual(["CAS-0000012"]);
  });

  it("does not invent a match for a typo-tolerant result", () => {
    expect(matches("phising", "Potential phishing")).toBeUndefined();
  });
});
